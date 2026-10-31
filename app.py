import os
import re
import shutil
import subprocess
from pathlib import Path

import bs4
import httpx
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import errors

# 1. Sustituido el parseo manual por python-dotenv (más seguro para producción)
load_dotenv()

# 2. Esquemas de Pydantic para forzar a Gemini a devolver una estructura estricta
class TailoredBullet(BaseModel):
    id: int = Field(description="El ID exacto de la viñeta original.")
    tailored_text: str = Field(description="El nuevo texto adaptado en LaTeX, incluyendo \\item al principio.")

class CVUpdate(BaseModel):
    replacements: list[TailoredBullet]


st.title("Overleaf CV Tailoring Agent")

repo_dir_input = st.text_input("Path to Local CV Directory", value="./CV_ESPECIFICOS")
job_url_input = st.text_input("Job Posting URL")
job_description_input = st.text_area(
    "Paste job description (use this if the posting site blocks access)",
    height=200,
)
compiler_choice = "pdflatex"
st.caption("PDF compiler: pdflatex")


def scrape_job_description(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:4000]


def tailor_latex_cv(tex_content, job_description, progress):
    client = genai.Client(http_options={"timeout": 60_000})
    
    # 3. Extraemos las viñetas con Regex para no depender del "Exact Match" del LLM
    # Busca \item seguido de cualquier cosa hasta el siguiente \item o \end{...}
    bullet_pattern = re.compile(r"\\item\s+.*?(?=\s*\\item|\s*\\end\{)", re.DOTALL)
    original_bullets = bullet_pattern.findall(tex_content)
    
    if not original_bullets:
        raise ValueError("No se encontraron viñetas (\\item) en el currículum.")
        
    bullets_dict = {i: bullet for i, bullet in enumerate(original_bullets)}
    bullets_list_str = "\n".join([f"ID {k}: {v.strip()}" for k, v in bullets_dict.items()])

    prompt = f"""
    You are an expert technical resume editor. 
    Analyze the Job Description and the LaTeX CV below. 
    
    Your task is to rewrite ONLY the experience bullet points to better align with the job description keywords.
    
    CRITICAL RULES:
    1. Review the EXTRACTED BULLETS below. Return ONLY the IDs of the experience bullet points you want to rewrite and their new text.
    2. Do NOT invent new job titles or fake experience. Reframe existing achievements.
    3. Ensure LaTeX special characters like %, $, &, #, _ are properly escaped.
    4. Projects must always be Galentreno and Peliculon-es, do not under any circumstances change them.

    --- JOB DESCRIPTION ---
    {job_description}

    --- LATEX CV CONTENT (For Context) ---
    {tex_content}
    
    --- EXTRACTED BULLETS (Select IDs from here) ---
    {bullets_list_str}
    """

    progress.write("Sending structured request to Gemini...")
    
    # 4. Pasamos el response_schema para garantizar que devuelve nuestro modelo Pydantic
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": CVUpdate,
            "temperature": 0.2
        }
    )
    
    if not response.parsed:
        raise ValueError("Gemini failed to return a valid JSON matching the required schema.")
        
    updates = response.parsed.replacements # type: ignore
    
    # Mapeamos los IDs devueltos a los textos originales extraídos
    replacements = {}
    for update in updates:
        if update.id in bullets_dict:
            original_text = bullets_dict[update.id]
            if original_text.strip() != update.tailored_text.strip():
                replacements[original_text] = update.tailored_text

    if not replacements:
        progress.write("No experience bullets were modified by the AI.")
        return tex_content

    # Reemplazo seguro de una sola pasada ordenando de mayor a menor longitud
    pattern = re.compile("|".join(re.escape(key) for key in sorted(replacements, key=len, reverse=True)))
    return pattern.sub(lambda match: replacements[match.group(0)], tex_content)


def validate_latex_compilation(repo_path, compiler="pdflatex"):
    if not shutil.which(compiler):
        return False, (
            f"{compiler} is not installed or not on PATH. "
            "Install a LaTeX distribution to generate the PDF."
        )
    cmd = [compiler, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, f"{compiler} compilation exceeded the 120-second limit."
    if result.returncode != 0:
        return False, result.stdout[-1500:]
    pdf_path = repo_path / "main.pdf"
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        return False, f"{compiler} finished without creating a non-empty main.pdf."
    return True, "LaTeX compiled successfully."


if st.button("Tailor and Generate PDF"):
    if not job_url_input and not job_description_input.strip():
        st.error("Enter a job URL or paste the job description.")
    else:
        repo_path = Path(repo_dir_input)
        main_tex = repo_path / "main.tex"
        if not main_tex.exists():
            st.error(f"main.tex not found in {repo_path}")
        elif not shutil.which(compiler_choice):
            st.error(
                f"{compiler_choice} is not installed or not on PATH. "
                "Install a LaTeX distribution to generate the PDF."
            )
        else:
            with st.status("Starting CV tailoring...", expanded=True) as progress:
                backup_tex = repo_path / "main.tex.bak"
                backup_created = False
                try:
                    job_desc = (
                        job_description_input.strip()
                        if job_description_input.strip()
                        else None
                    )
                    if job_desc is None:
                        progress.update(label="Fetching job description...")
                        job_desc = scrape_job_description(job_url_input)
                    else:
                        progress.update(label="Using the pasted job description...")

                    progress.update(label="Reading your CV...")
                    original_tex = main_tex.read_text(encoding="utf-8")
                    progress.update(label="Generating tailored bullets with Gemini...")
                    tailored_tex = tailor_latex_cv(original_tex, job_desc, progress)

                    progress.update(label="Saving tailored CV...")
                    shutil.copy2(main_tex, backup_tex)
                    backup_created = True
                    main_tex.write_text(tailored_tex, encoding="utf-8")

                    progress.update(label=f"Compiling PDF with {compiler_choice}...")
                    success, log_msg = validate_latex_compilation(
                        repo_path, compiler=compiler_choice
                    )

                    if not success:
                        backup_tex.replace(main_tex)
                        backup_created = False
                        progress.update(
                            label="LaTeX compilation failed.", state="error"
                        )
                        st.error("LaTeX compilation failed. Reverted changes.")
                        st.code(log_msg)
                    else:
                        backup_tex.unlink(missing_ok=True)
                        backup_created = False
                        progress.update(
                            label="CV tailoring complete.", state="complete"
                        )
                        st.success("CV tailored and compiled to PDF successfully!")
                except httpx.HTTPStatusError as e:
                    progress.update(
                        label="Could not fetch the job description.", state="error"
                    )
                    if e.response.status_code == 403:
                        st.error(
                            "The job site denied automated access (HTTP 403). "
                            "Paste the job description above and try again."
                        )
                    else:
                        st.error(
                            f"Could not fetch the job description "
                            f"(HTTP {e.response.status_code})."
                        )
                except httpx.TimeoutException:
                    progress.update(label="The request timed out.", state="error")
                    st.error(
                        "A network request timed out. If the job site is blocking access, "
                        "paste the job description and try again."
                    )
                except errors.APIError as e:
                    progress.update(
                        label="Gemini could not complete the request.", state="error"
                    )
                    st.error(f"Gemini API error: {e}")
                except Exception as e:
                    if backup_created and backup_tex.exists():
                        try:
                            backup_tex.replace(main_tex)
                        except OSError as restore_error:
                            st.error(f"Could not restore the original CV: {restore_error}")
                    progress.update(label="CV processing failed.", state="error")
                    st.error(f"An error occurred: {e}")

repo_path = Path(repo_dir_input)
pdf_path = repo_path / "main.pdf"
if repo_path.exists() and pdf_path.exists():
    with open(pdf_path, "rb") as pdf_file:
        st.download_button(
            label="Download Tailored CV (PDF)",
            data=pdf_file,
            file_name="tailored_cv.pdf",
            mime="application/pdf",
        )