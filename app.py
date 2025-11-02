import streamlit as st
import docx2txt
import pdfplumber
import google.generativeai as genai
import base64
from fpdf import FPDF
import io
import re
import textwrap

# --- Page Setup ---
st.set_page_config(page_title="Gemini ATS Resume Optimizer", layout="centered")
st.title("🤖 ATS Resume Optimizer with Gemini AI")

# --- Step 1: API Key ---
st.header("🔐 Step 1: Enter your Gemini API Key")
api_key = st.text_input("Enter your Gemini API Key", type="password")

# --- File/Text Extraction ---
def extract_text(uploaded_file):
    if uploaded_file is None:
        return ""
    if uploaded_file.name.endswith(".pdf"):
        with pdfplumber.open(uploaded_file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif uploaded_file.name.endswith(".docx"):
        return docx2txt.process(uploaded_file)
    else:
        return uploaded_file.read().decode("utf-8")

# --- Markdown cleanup (convert **text** to bold, *text* to italic) ---
def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    return text

# --- Text to PDF (safe wrapping for long lines) ---
def convert_to_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for line in text.split('\n'):
        wrapped_lines = textwrap.wrap(line, width=100, break_long_words=True)
        for subline in wrapped_lines:
            try:
                pdf.multi_cell(0, 10, subline)
            except Exception:
                safe_line = subline.encode("ascii", errors="ignore").decode()
                pdf.multi_cell(0, 10, safe_line)
    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer


# --- Gemini model discovery ---
def get_flash_models_from_genai():
    """
    Discover available Gemini models from the genai SDK that match the pattern
    gemini-<version>-flash (e.g. gemini-2.5-flash). Returns a list of model names
    sorted by version (newest first). If discovery fails or finds nothing, returns []
    """
    try:
        resp = None
        # Try several possible list APIs on the SDK
        if hasattr(genai, "list_models"):
            resp = genai.list_models()
        elif hasattr(genai, "models") and hasattr(genai.models, "list"):
            resp = genai.models.list()
        elif hasattr(genai, "Model") and hasattr(genai.Model, "list"):
            # fallback pattern
            resp = genai.Model.list()

        items = []
        if resp is None:
            items = []
        elif isinstance(resp, dict) and "models" in resp:
            items = resp["models"]
        elif hasattr(resp, "models"):
            items = resp.models
        elif isinstance(resp, (list, tuple)):
            items = resp
        else:
            # try to treat resp as iterable
            try:
                items = list(resp)
            except Exception:
                items = []

        flash_models = []
        for it in items:
            name = None
            if isinstance(it, dict):
                # common keys: 'name', 'id', 'model'
                name = it.get("name") or it.get("id") or it.get("model")
            else:
                name = getattr(it, "name", None) or getattr(it, "id", None) or getattr(it, "model", None)
            if not name:
                # last resort: string representation
                try:
                    name = str(it)
                except Exception:
                    name = None
            if not name:
                continue

            # match patterns like gemini-2-flash, gemini-2.5-flash, gemini-2.5.1-flash
            m = re.match(r"^gemini-(\d+(?:\.\d+)*)-flash$", name)
            if m:
                ver = m.group(1)
                # convert version string to tuple of ints for robust sorting
                try:
                    ver_tuple = tuple(int(p) for p in ver.split("."))
                except Exception:
                    ver_tuple = (0,)
                flash_models.append((ver_tuple, name))

        # sort by version descending (newest first)
        flash_models.sort(reverse=True, key=lambda x: x[0])
        return [name for _, name in flash_models]
    except Exception:
        return []


# --- Main Flow ---
if api_key:
    genai.configure(api_key=api_key)
    st.success("✅ API Key validated!")

    # --- Step 2: Resume + JD Input ---
    st.header("📄 Step 2: Provide Resume and Job Description")

    col1, col2 = st.columns(2)

    with col1:
        resume_file = st.file_uploader("📂 Upload Resume", type=["pdf", "docx", "txt"])
        resume_text_input = st.text_area("✍️ Or Paste Resume Text", height=200)
    with col2:
        jd_file = st.file_uploader("📂 Upload Job Description", type=["pdf", "docx", "txt"])
        jd_text_input = st.text_area("✍️ Or Paste Job Description Text", height=200)

    # Resolve text input (prioritize file over pasted text)
    resume_text = extract_text(resume_file) if resume_file else resume_text_input.strip()
    jd_text = extract_text(jd_file) if jd_file else jd_text_input.strip()

    if resume_text and jd_text:
        st.success("✅ Resume and Job Description loaded successfully!")
        st.header("🤖 Step 3: Gemini Resume Optimization")

        prompt = f"""
You are a resume optimization assistant. I am applying for the following job role:

JOB DESCRIPTION:
{jd_text}

Here is my current resume:
{resume_text}

Please rewrite my resume to better match the job description using appropriate keywords, phrasing, and skills. Ensure it is still truthful and reflects the resume structure (Summary, Work Experience, Education, Skills, and Certifications). Keep the output as plain text resume content.
"""

        try:
            with st.spinner("⏳ Optimizing your resume using Gemini AI..."):
                # Dynamically discover candidate flash models from the SDK, with fallback defaults
                candidate_models = get_flash_models_from_genai()
                if candidate_models:
                    st.info(f"Discovered gemini flash models: {candidate_models}")
                else:
                    # safe fallback list if SDK doesn't provide model listing or none found
                    candidate_models = [
                        "gemini-2.5-flash",
                        "gemini-2.1-flash",
                        "gemini-1.5-flash",
                        "gemini-1.0-flash",
                    ]
                    st.info(f"Using fallback gemini flash models: {candidate_models}")

                optimized_resume = None
                last_error = None

                for model_name in candidate_models:
                    # only try models that match the gemini-<version>-flash format
                    if not re.match(r"^gemini-(\d+(?:\.\d+)*)-flash$", model_name):
                        st.warning(f"Skipping invalid model name format: {model_name}")
                        continue
                    try:
                        st.info(f"Trying model: {model_name}")
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(prompt)
                        # response.text is expected; fall back to str(response) if not available
                        optimized_resume = getattr(response, 'text', None) or str(response)
                        st.success(f"✅ Optimized with {model_name}")
                        break
                    except Exception as model_err:
                        last_error = model_err
                        st.warning(f"Model {model_name} failed: {model_err}")
                        # try the next model

                if not optimized_resume:
                    # No models succeeded
                    raise Exception(f"All candidate Gemini flash models failed. Last error: {last_error}")

            # Step 4: Display output
            st.markdown("📝 **Optimized Resume**", unsafe_allow_html=True)
            st.markdown(clean_markdown(optimized_resume), unsafe_allow_html=True)

            # Step 5: Downloads
            st.header("📩 Step 4: Download Your Optimized Resume")

            # TXT Download
            b64_txt = base64.b64encode(optimized_resume.encode()).decode()
            st.markdown(
                f'<a href="data:file/txt;base64,{b64_txt}" download="Optimized_Resume.txt">📥 Download as .TXT</a>',
                unsafe_allow_html=True
            )

            # PDF Download (safe version)
            pdf_buffer = convert_to_pdf(optimized_resume)
            st.download_button("📄 Download as PDF", data=pdf_buffer, file_name="Optimized_Resume.pdf", mime="application/pdf")

        except Exception as e:
            st.error(f"❌ Gemini API Error: {str(e)}")

    else:
        st.info("📥 Please upload or paste both your resume and job description.")
else:
    st.warning("🔑 Please enter a valid Gemini API Key to continue.")
