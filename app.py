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

Please rewrite my resume to better match the job description using appropriate keywords, phrasing, and skills. Ensure it is still truthful and reflects the resume structure (Summary, Work Experience, Projects, Education, etc.). Return only the optimized resume text.
        """

        try:
            with st.spinner("⏳ Optimizing your resume using Gemini AI..."):
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt)
                optimized_resume = response.text

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
