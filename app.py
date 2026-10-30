import os
import json
import re
import shutil
import subprocess
from pathlib import Path
import bs4
import httpx
import streamlit as st
from google import genai
from google.genai import errors


def load_dotenv_file(path=Path(".env")):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator and key.strip():
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


load_dotenv_file()

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
    prompt = f"""
    You are an expert technical resume editor. 
    Analyze the Job Description and the LaTeX CV below. 
    
    Your task is to rewrite ONLY the experience bullet points in the CV to better align with the job description keywords.
    
    CRITICAL RULES:
    1. Return your response as a valid JSON object where keys are the EXACT original bullet points (\\item text) and values are the tailored replacement bullet points.
    2. Do NOT invent new job titles or fake experience. Reframe existing achievements.
    3. Ensure LaTeX special characters like %, $, &, #, _ are properly escaped.
    4. Return ONLY valid JSON.
    5. Projects must always be Galentreno and Peliculon-es, do not under any circumstances change them.

    --- JOB DESCRIPTION ---
    {job_description}

    --- LATEX CV CONTENT ---
    {tex_content}
    """

    progress.write("Sending structured request to Gemini...")
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )
    
    try:
        if response.text is None:
            raise ValueError("Gemini returned an empty response.")
        replacements = json.loads(response.text)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON response from Gemini: {e}")

    if not isinstance(replacements, dict) or not replacements:
        raise ValueError("Gemini must return a non-empty JSON object of bullet replacements.")
    if any(
        not isinstance(original, str)
        or not original.strip()
        or not isinstance(tailored, str)
        or not tailored.strip()
        for original, tailored in replacements.items()
    ):
        raise ValueError("Gemini returned an invalid bullet replacement.")

    missing = [original for original in replacements if original not in tex_content]
    if missing:
        raise ValueError("Gemini returned bullet text that does not exactly match the CV.")

    # Replace against the original text in one pass so a replacement cannot be
    # modified again by a later key in the response.
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
                except errors.ServerError as e:
                    progress.update(
                        label="Gemini could not complete the request.", state="error"
                    )
                    if e.code == 504:
                        st.error(
                            "Gemini timed out again while generating the CV. "
                            "No partial output was saved. Please try again."
                        )
                    else:
                        st.error(f"Gemini returned server error {e.code}: {e.message}")
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