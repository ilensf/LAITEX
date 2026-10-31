import os
import re
import shutil
import subprocess
from pathlib import Path
import time
import json

import bs4
import httpx
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import errors
from groq import Groq

load_dotenv()

class CVUpdate(BaseModel):
    company_name: str = Field(description="Name of the company offering the job position. If unknown, return 'UNK'.")
    full_tailored_latex: str = Field(description="The complete, fully compilable LaTeX source code of the tailored (and translated if needed) CV. Must contain the entire document from \documentclass to \end{document}.")

st.title("Overleaf CV Tailoring Agent")

repo_dir_input = st.text_input("Path to Local CV Directory", value="./CV_ESPECIFICOS")
job_url_input = st.text_input("Job Posting URL")
job_description_input = st.text_area(
    "Paste job description (use this if the posting site blocks access)",
    height=200,
)
# NUEVO CAMPO: Para que los usuarios decidan qué palabras/proyectos proteger
immutable_terms_input = st.text_input(
    "Immutable Projects/Terms (optional, comma-separated)", 
    help="Names of projects, technologies, or specific terms the AI should NEVER change.",
    placeholder="e.g. Galentreno, Peliculon.es"
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


def _run_gemini(prompt):
    client = genai.Client(http_options={"timeout": 300_000})
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
        raise ValueError("Gemini failed to return a valid JSON.")
    return response.parsed.company_name, response.parsed.full_tailored_latex


def _run_groq(prompt):
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("No GROQ_API_KEY found in .env.")
    
    groq_prompt = prompt + "\n\nIMPORTANT: You must return ONLY a valid JSON object with exactly two keys: 'company_name' (string) and 'full_tailored_latex' (string containing the complete LaTeX code)."
    groq_client = Groq(api_key=groq_api_key)
    completion = groq_client.chat.completions.create(
        model="llama3-70b-8192", 
        messages=[
            {"role": "system", "content": "You are an expert technical resume editor and translator. Output strictly in JSON format."},
            {"role": "user", "content": groq_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=300
    )
    
    raw_json = completion.choices[0].message.content
    parsed_dict = json.loads(raw_json)
    
    comp_name = parsed_dict.get("company_name", "UNK")
    tex = parsed_dict.get("full_tailored_latex", "")
    
    if not tex:
        raise ValueError("Groq failed to return the 'full_tailored_latex' key.")
    return comp_name, tex


def tailor_latex_cv(tex_content, job_description, immutable_terms, progress, error_log=None, engine="gemini"):
    # REGLA 5 DINÁMICA: Se adapta si el usuario introdujo proyectos a proteger o no.
    if immutable_terms.strip():
        rule_5 = f"5. IMMUTABLE TERMS: The following projects/terms must remain exactly as they are: {immutable_terms.strip()}. Do not change their names or core functionality descriptions under any circumstances."
    else:
        rule_5 = "5. IMMUTABLE TERMS: Do not change the proper names of any existing projects, companies, or institutions present in the CV."

    prompt = f"""
    You are an expert technical resume editor and translator. 
    Analyze the Job Description and the LaTeX CV below. 
    
    CRITICAL RULES:
    1. TAILORING: Rewrite the experience bullet points to better align with the job description keywords. Do NOT invent fake experience, just reframe existing achievements.
    2. TRANSLATION: Detect the language of the Job Description. If it is in ENGLISH, you MUST translate the ENTIRE CV into English. This includes section headers, summary, skills, experience, AND all LaTeX comments that act as structural headers (e.g., %-----------PROYECTOS DESTACADOS----------- must become %-----------FEATURED PROJECTS-----------). If it is in SPANISH, keep the CV in Spanish.
    3. PRESERVE STRUCTURE: You must return the COMPLETE and fully valid LaTeX document. Do not remove any LaTeX packages or document structure.
    4. ESCAPING: Ensure LaTeX special characters like %, $, &, #, _ are properly escaped.
    {rule_5}
    6. COMPANY NAME: Extract the company name offering the position.

    --- JOB DESCRIPTION ---
    {job_description}

    --- LATEX CV CONTENT (Current State) ---
    {tex_content}
    """

    if error_log:
        prompt += f"""
        
        --- CRITICAL COMPILATION ERROR ---
        Your previous attempt at generating the LaTeX code caused a compiler error. 
        Here is the compiler log:
        
        {error_log[-1000:]} 
        
        Find the unescaped character or invalid LaTeX syntax you introduced in the current LaTeX CV content and FIX IT in your new response. Ensure the output is a valid, compilable LaTeX document.
        """

    if engine == "gemini":
        try:
            progress.write("Sending request to Gemini (Primary)...")
            company_name_full, new_tex = _run_gemini(prompt)
        except Exception as e:
            progress.write(f"Gemini unavailable ({e}). Falling back to Groq API (Llama 3)...")
            company_name_full, new_tex = _run_groq(prompt)
    else:
        try:
            progress.write("Sending request to Groq (Primary)...")
            company_name_full, new_tex = _run_groq(prompt)
        except Exception as e:
            progress.write(f"Groq unavailable ({e}). Falling back to Gemini...")
            company_name_full, new_tex = _run_gemini(prompt)

    clean_name = re.sub(r'[^A-Za-z0-9]', '', company_name_full)
    company_prefix = clean_name[:3].upper() if clean_name else "UNK"
    
    return new_tex, company_prefix


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


# --- UI: BOTONES DE SELECCIÓN ---
st.write("### AI Engine Selection")
col1, col2 = st.columns(2)
with col1:
    run_gemini = st.button("🚀 Tailor with Gemini (Default)", type="primary", use_container_width=True)
with col2:
    run_groq = st.button("⚡ Tailor with Groq", type="secondary", use_container_width=True)

if run_gemini or run_groq:
    selected_engine = "groq" if run_groq else "gemini"
    
    if not job_url_input and not job_description_input.strip():
        st.error("Enter a job URL or paste the job description.")
    else:
        repo_path = Path(repo_dir_input)
        main_tex = repo_path / "main.tex"
        
        repo_path.mkdir(parents=True, exist_ok=True)
        
        if not main_tex.exists():
            st.error(f"main.tex not found in {repo_path}")
        elif not shutil.which(compiler_choice):
            st.error(
                f"{compiler_choice} is not installed or not on PATH. "
                "Install a LaTeX distribution to generate the PDF."
            )
        else:
            with st.status(f"Starting full CV tailoring agent with {selected_engine.capitalize()}...", expanded=True) as progress:
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
                    
                    shutil.copy2(main_tex, backup_tex)
                    backup_created = True
                    
                    MAX_RETRIES = 3
                    error_log = None
                    success = False
                    extracted_prefix = "UNK"
                    
                    current_tex = original_tex 
                    
                    for attempt in range(MAX_RETRIES):
                        progress.update(label=f"Attempt {attempt + 1}/{MAX_RETRIES}: Rewriting CV...")
                        
                        # Pasamos la variable immutable_terms_input a la función
                        tailored_tex, current_prefix = tailor_latex_cv(
                            current_tex, job_desc, immutable_terms_input, progress, error_log, engine=selected_engine
                        )
                        extracted_prefix = current_prefix

                        progress.update(label="Saving temporary tailored CV...")
                        main_tex.write_text(tailored_tex, encoding="utf-8")
                        current_tex = tailored_tex

                        progress.update(label=f"Compiling PDF with {compiler_choice}...")
                        success, log_msg = validate_latex_compilation(repo_path, compiler=compiler_choice)

                        if success:
                            break
                        else:
                            progress.write(f"LaTeX compilation failed on attempt {attempt + 1}. Asking AI to fix it...")
                            error_log = log_msg

                    if not success:
                        backup_tex.replace(main_tex)
                        backup_created = False
                        progress.update(label="LaTeX compilation failed after all retries.", state="error")
                        st.error(f"The agent failed to generate valid LaTeX after {MAX_RETRIES} attempts. main.tex reverted.")
                        with st.expander("View Final LaTeX Error Log"):
                            st.code(error_log)
                    else:
                        compiled_pdf = repo_path / "main.pdf"
                        final_pdf_name = f"CV_ATS_{extracted_prefix}.pdf"
                        
                        final_pdf_path = repo_path / final_pdf_name
                        if final_pdf_path.exists():
                            short_ts = str(int(time.time()))[-4:]
                            final_pdf_name = f"CV_ATS_{extracted_prefix}_{short_ts}.pdf"
                            final_pdf_path = repo_path / final_pdf_name
                        
                        shutil.copy2(compiled_pdf, final_pdf_path)
                        compiled_pdf.unlink(missing_ok=True)
                        
                        backup_tex.replace(main_tex)
                        backup_created = False
                        
                        progress.update(label="CV tailoring complete.", state="complete")
                        st.success(f"CV tailored successfully! The PDF has been saved automatically in '{repo_path}' as '{final_pdf_name}'. The original main.tex has been restored.")
                        
                except Exception as e:
                    if backup_created and backup_tex.exists():
                        try:
                            backup_tex.replace(main_tex)
                        except OSError as restore_error:
                            st.error(f"Could not restore the original CV: {restore_error}")
                    progress.update(label="CV processing failed.", state="error")
                    st.error(f"An error occurred: {e}")