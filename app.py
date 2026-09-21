import csv
import io
import json
import os

# app.py
import streamlit as st
import requests

st.set_page_config(page_title="Medical Custom Tailoring Portal", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
.hero { padding: 1.5rem 1.75rem; border-radius: 18px; background: linear-gradient(135deg, #102a43, #1f6f8b); color: white; margin-bottom: 1.5rem; }
.hero h1 { margin: 0; font-size: 2.2rem; }
.hero p { margin: .4rem 0 0; color: #d9f0f2; }
[data-testid="stMetric"] { background: #f4f8f9; border: 1px solid #dce8eb; padding: 1rem; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
if not BASE_URL.startswith(("http://", "https://")):
    BASE_URL = f"https://{BASE_URL}"

if "access_token" not in st.session_state:
    st.session_state.access_token = None


def api_request(method, path, **kwargs):
    if not st.session_state.access_token:
        st.error("Please log in to access the measurement records.")
        return None
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {st.session_state.access_token}"
    try:
        response = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"API request failed: {error}")
        return None


def show_record_image(record_id, caption="Stored measurement diagram"):
    if not st.session_state.access_token:
        return False
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/measurements/{record_id}/image",
            headers={"Authorization": f"Bearer {st.session_state.access_token}"},
            timeout=30,
        )
        if response.status_code == 200:
            st.image(io.BytesIO(response.content), caption=caption, use_container_width=True)
            return True
    except requests.RequestException:
        pass
    return False


if not st.session_state.access_token:
    st.markdown('<div class="hero"><h1>Medical Measurement Portal</h1><p>Sign in to access patient records, diagrams, search, and analytics.</p></div>', unsafe_allow_html=True)
    st.subheader("Sign in")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Sign in")
    if login_submitted:
        try:
            response = requests.post(
                f"{BASE_URL}/token",
                data={"username": username, "password": password},
                timeout=30,
            )
            response.raise_for_status()
            st.session_state.access_token = response.json()["access_token"]
            st.rerun()
        except requests.RequestException:
            st.error("Invalid username or password.")
    st.stop()


with st.sidebar:
    st.title("App Navigation")
    st.success("Logged in")
    if st.button("Log out"):
        st.session_state.access_token = None
        st.rerun()

# Dashboard Sidebar Navigation
page = st.sidebar.radio("Go to", ["Dashboard & RAG Search", "New Entry (Form/OCR)", "Analytics"])

if page == "New Entry (Form/OCR)":
    st.header("Record Patient Measurements")
    tab1, tab2 = st.tabs(["Manual Input", "Upload OCR/PDF/Image"])
    
    with tab1:
        with st.form("manual_form"):
            col1, col2 = st.columns(2)
            patient_id = col1.text_input("Patient ID")
            doc_id = col1.text_input("Doctor ID / Name")
            chest = col1.number_input("Chest (inches)", min_value=10.0, max_value=80.0)
            waist = col1.number_input("Waist (inches)", min_value=10.0, max_value=80.0)
            hips = col1.number_input("Hips (inches)", min_value=10.0, max_value=80.0)
            shoulder = col2.number_input("Shoulder Width (inches)", min_value=5.0, max_value=40.0)
            arm_length = col2.number_input("Arm Length (inches)", min_value=0.0, max_value=60.0)
            inseam = col2.number_input("Inseam (inches)", min_value=10.0, max_value=50.0)
            notes = st.text_area("Special Tailoring Notes")
            
            submitted = st.form_submit_button("Save Record")
            if submitted:
                result = api_request(
                    "POST",
                    "/api/v1/measurements/manual",
                    json={
                        "patient_id": patient_id,
                        "doctor_id": doc_id,
                        "chest": chest,
                        "waist": waist,
                        "hips": hips,
                        "shoulder": shoulder,
                        "arm_length": arm_length,
                        "inseam": inseam,
                        "notes": notes,
                    },
                )
                if result:
                    st.success(f"Record saved to ChromaDB: {result['record_id']}")

    with tab2:
        uploaded_file = st.file_uploader("Upload handwritten logbook scan (PDF/PNG/JPG)", type=["pdf", "png", "jpg", "jpeg"])
        if uploaded_file and uploaded_file.type.startswith("image/"):
            st.image(uploaded_file, caption="Uploaded body diagram / measurement image", use_container_width=True)
        if uploaded_file and st.button("Process Document"):
            result = api_request(
                "POST",
                "/api/v1/measurements/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
            )
            if result:
                st.success(f"Record saved to ChromaDB: {result['record_id']}")
                st.json(result["parsed_data"])

elif page == "Dashboard & RAG Search":
    st.markdown('<div class="hero"><h1>Measurement Search</h1><p>Find patient records and tailoring notes from your ChromaDB archive.</p></div>', unsafe_allow_html=True)
    query = st.text_input("Search records (e.g., 'Find doctors who need custom broad-shoulder adjustments')")
    if query:
        result = api_request(
            "POST",
            "/api/v1/measurements/query",
            json={"query_text": query, "n_results": 5},
        )
        if result:
            if result["results"]:
                for item in result["results"]:
                    metadata = item["metadata"]
                    st.write(f"**Patient {metadata.get('patient_id', '-')}** | Doctor: {metadata.get('doctor_id', '-')}")
                    st.dataframe([{
                        "Chest": metadata.get("chest", "-"),
                        "Waist": metadata.get("waist", "-"),
                        "Hips": metadata.get("hips", "-"),
                        "Shoulder": metadata.get("shoulder", "-"),
                        "Arm length": metadata.get("arm_length", "-"),
                        "Inseam": metadata.get("inseam", "-"),
                    }], hide_index=True, use_container_width=True)
                    st.caption(f"Record: {item['id']} | {metadata.get('notes', '')}")
                    show_record_image(item["id"])
            else:
                st.info("No matching records found.")

elif page == "Analytics":
    st.markdown('<div class="hero"><h1>Measurement Analytics</h1><p>A clean view of your patient measurement archive.</p></div>', unsafe_allow_html=True)
    result = api_request("GET", "/api/v1/measurements/analytics")
    if result:
        all_records = result["records"]
        doctors = sorted({record["doctor_id"] for record in all_records if record.get("doctor_id")})
        selected_doctor = st.selectbox("Filter by doctor name or ID", ["All doctors"] + doctors)
        records = (
            all_records
            if selected_doctor == "All doctors"
            else [record for record in all_records if record.get("doctor_id") == selected_doctor]
        )

        fields = ["chest", "waist", "hips", "shoulder", "arm_length", "inseam"]
        averages = {
            field: round(sum(record[field] for record in records if record.get(field) is not None) / len([record for record in records if record.get(field) is not None]), 2)
            if any(record.get(field) is not None for record in records)
            else None
            for field in fields
        }
        doctor_counts = {selected_doctor: len(records)} if selected_doctor != "All doctors" else result["records_by_doctor"]
        st.caption(f"Showing {len(records)} unique measurement records")
        metric_columns = st.columns(4)
        metric_columns[0].metric("Unique records", len(records))
        metric_columns[1].metric("Patients", len({record["patient_id"] for record in records}))
        metric_columns[2].metric("Doctors", len({record["doctor_id"] for record in records}))
        metric_columns[3].metric("Latest date", max((record["created_at"] for record in records), default="-"))

        st.subheader("Average measurements (inches)")
        average_columns = st.columns(6)
        labels = [("Chest", "chest"), ("Waist", "waist"), ("Hips", "hips"), ("Shoulder", "shoulder"), ("Arm", "arm_length"), ("Inseam", "inseam")]
        for column, (label, field) in zip(average_columns, labels):
            column.metric(label, averages[field] if averages[field] is not None else "-")

        left, right = st.columns(2)
        with left:
            st.subheader("Records by doctor")
            st.bar_chart(doctor_counts)
        with right:
            st.subheader("Measurement profile")
            profile = {label: averages[field] for label, field in labels if averages[field] is not None}
            st.bar_chart(profile)

        st.subheader("All measurement records")
        st.dataframe(records, hide_index=True, use_container_width=True)

        download_columns = st.columns(2)
        csv_buffer = io.StringIO()
        csv_writer = csv.DictWriter(csv_buffer, fieldnames=[
            "record_id", "patient_id", "doctor_id", *fields, "notes", "created_at", "image_file"
        ])
        csv_writer.writeheader()
        csv_writer.writerows(records)
        download_columns[0].download_button(
            "Download CSV",
            csv_buffer.getvalue(),
            file_name="measurement_dashboard.csv",
            mime="text/csv",
            use_container_width=True,
        )
        download_columns[1].download_button(
            "Download JSON",
            json.dumps({"doctor": selected_doctor, "records": records, "averages": averages}, indent=2),
            file_name="measurement_dashboard.json",
            mime="application/json",
            use_container_width=True,
        )

        image_records = [record for record in records if record.get("image_file")]
        if image_records:
            selected_record = st.selectbox(
                "Show stored diagram",
                image_records,
                format_func=lambda record: f"{record['patient_id']} | {record['doctor_id']} | {record['record_id']}",
            )
            show_record_image(selected_record["record_id"], "Stored body diagram")
        else:
            st.info("No uploaded diagrams are linked to the current records.")