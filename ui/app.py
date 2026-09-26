import streamlit as st
import pandas as pd
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_loader import DataLoader
from src.product_master import ProductMaster
from src.inventory_engine import InventoryEngine
from src.low_stock_engine import LowStockEngine
from src.query_parser import QueryParser
from src.ai_assistant import AIAssistant
from src.config import LLM_PROVIDER, LLM_MODEL, GROQ_API_KEY, GEMINI_API_KEY

# Configure Streamlit Page
st.set_page_config(
    page_title="Symax AI Stock Assistant",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F3F4F6;
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #2563EB;
    }
    .warning-box {
        background-color: #FEF3C7;
        border-left: 4px solid #F59E0B;
        padding: 0.75rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
    }
    .source-tag {
        display: inline-block;
        background-color: #E0E7FF;
        color: #3730A3;
        padding: 2px 8px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.85rem;
        margin-right: 4px;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_services():
    loader = DataLoader()
    pm = ProductMaster(loader)
    inv = InventoryEngine(loader, pm)
    low_stk = LowStockEngine(loader, pm, inv)
    parser = QueryParser()
    asst = AIAssistant(loader, pm, inv, low_stk, parser)
    return loader, pm, inv, low_stk, asst


loader, product_master, inventory_engine, low_stock_engine, assistant = get_services()

# Sidebar Info & Status
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/chemistry.png", width=64)
    st.markdown("### **Symax Laboratories**")
    st.markdown("##### *AI Stock Assistant Platform*")
    st.divider()

    st.markdown("#### ⚙️ **System Configuration**")
    active_llm = "Groq (Llama-3.3/GPT-OSS)" if GROQ_API_KEY else ("Gemini" if GEMINI_API_KEY else "Deterministic Demo Mode")
    st.info(f"**Active Engine**: `{active_llm}`")
    st.caption("Deterministic mathematical calculations are enforced in all modes. LLMs only extract queries and explain results.")

    st.divider()
    st.markdown("#### 📊 **Dataset Metrics**")
    st.write(f"- Total ERP Records: **{len(loader.get_stock_data())}**")
    st.write(f"- Unique Formulations: **{len(product_master.get_all_products())}**")
    st.write(f"- Quality Issues Logged: **{len(loader.get_data_quality_report())}**")

# Main Header
st.markdown("<div class='main-header'>🧪 Symax AI Stock Assistant</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Explainable, multi-facility inventory intelligence for Symax Laboratories Pvt. Ltd.</div>", unsafe_allow_html=True)

# 5 Main Tabs
tab_chat, tab_explorer, tab_low_stock, tab_quality, tab_purchase = st.tabs([
    "💬 AI Stock Chat",
    "🔍 Inventory Explorer",
    "📉 Low Stock Dashboard",
    "📋 Data Quality Report",
    "🛒 Purchase Requirements"
])

# -----------------------------------------------------------------------------
# TAB 1: AI STOCK CHAT
# -----------------------------------------------------------------------------
with tab_chat:
    st.markdown("### 💬 Ask Questions About Chemical Stock")
    st.caption("Ask questions in natural language. Click any quick prompt below or type your own question.")

    # Quick Prompt Chips
    col1, col2, col3 = st.columns(3)
    quick_query = None
    with col1:
        if st.button("📌 Stock of CAS 109-72-8"):
            quick_query = "What is the stock of CAS 109-72-8?"
        if st.button("📌 Stock in Hyderabad"):
            quick_query = "How much is available in Hyderabad?"
        if st.button("📌 Stock in Bangalore"):
            quick_query = "How much is available in Bangalore?"
    with col2:
        if st.button("📌 n-Butyllithium 1.6 M in Hexane"):
            quick_query = "What is the stock of n-Butyllithium 1.6 M in Hexane?"
        if st.button("📌 Concentrations for CAS 109-72-8"):
            quick_query = "Which concentrations are available for CAS 109-72-8?"
    with col3:
        if st.button("📌 Products Below Minimum Stock"):
            quick_query = "Which products are below minimum stock?"
        if st.button("📌 In Hyderabad but not Bangalore"):
            quick_query = "Which products are available in Hyderabad but not Bangalore?"

    # Chat history state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display Chat Messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "warnings" in msg and msg["warnings"]:
                for w in msg["warnings"]:
                    st.warning(f"⚠️ {w}")

    # User Input
    user_input = st.chat_input("Ask about chemical inventory, locations, concentrations...")
    prompt_to_run = quick_query if quick_query else user_input

    if prompt_to_run:
        st.session_state.messages.append({"role": "user", "content": prompt_to_run})
        with st.chat_message("user"):
            st.markdown(prompt_to_run)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing stock records and calculating inventory..."):
                response = assistant.process_query(prompt_to_run)

                direct_ans = getattr(response, "direct_answer", getattr(response, "answer", ""))
                detailed_exp = getattr(response, "detailed_explanation", "")
                warnings_list = getattr(response, "warnings", [])
                clarif_needed = getattr(response, "clarification_needed", False)
                clarif_opts = getattr(response, "clarification_options", [])

                st.markdown(direct_ans)
                if detailed_exp:
                    st.markdown("---")
                    st.markdown(f"**Calculation & Grounding Explanation:**\n{detailed_exp}")

                if warnings_list:
                    for w in warnings_list:
                        st.warning(f"⚠️ {w}")

                if clarif_needed and clarif_opts:
                    st.info(f"💡 **Suggested Clarifications:** {', '.join(clarif_opts)}")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{direct_ans}\n\n{detailed_exp}" if detailed_exp else direct_ans,
                    "warnings": warnings_list
                })

# -----------------------------------------------------------------------------
# TAB 2: INVENTORY EXPLORER
# -----------------------------------------------------------------------------
with tab_explorer:
    st.markdown("### 🔍 Inventory Explorer")
    st.caption("Filter and explore raw & normalized chemical stock records.")

    stock_df = loader.get_stock_data().copy()

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        cas_options = ["All"] + sorted(stock_df["norm_CAS_Number"].unique().tolist())
        selected_cas = st.selectbox("Filter CAS Number", cas_options)
    with col_f2:
        prod_options = ["All"] + sorted(stock_df["norm_Product_Name"].unique().tolist())
        selected_prod = st.selectbox("Filter Product Name", prod_options)
    with col_f3:
        loc_options = ["All"] + sorted(stock_df["norm_Location"].unique().tolist())
        selected_loc = st.selectbox("Filter Location", loc_options)
    with col_f4:
        unit_options = ["All"] + sorted(stock_df["Unit"].unique().tolist())
        selected_unit = st.selectbox("Filter Unit", unit_options)

    filtered_df = stock_df.copy()
    if selected_cas != "All":
        filtered_df = filtered_df[filtered_df["norm_CAS_Number"] == selected_cas]
    if selected_prod != "All":
        filtered_df = filtered_df[filtered_df["norm_Product_Name"] == selected_prod]
    if selected_loc != "All":
        filtered_df = filtered_df[filtered_df["norm_Location"] == selected_loc]
    if selected_unit != "All":
        filtered_df = filtered_df[filtered_df["Unit"] == selected_unit]

    m1, m2, m3 = st.columns(3)
    pos_filtered = filtered_df[(filtered_df["Quantity"] > 0) & (filtered_df["is_eligible_for_stock"] == True)]
    m1.metric("Matching Records", len(filtered_df))
    m2.metric("Positive Stock Sum (Litre)", f"{pos_filtered[pos_filtered['Unit'] == 'Litre']['Quantity'].sum():,.0f} L")
    m3.metric("Positive Stock Sum (Kg)", f"{pos_filtered[pos_filtered['Unit'] == 'Kg']['Quantity'].sum():,.0f} Kg")

    show_normalized = st.checkbox("Show Normalized Columns Side-by-Side with Original Data", value=True)

    if show_normalized:
        display_cols = [
            "Stock_ID", "CAS_Number", "norm_CAS_Number", "Product_Name",
            "norm_Product_Name", "Concentration", "norm_Concentration",
            "Quantity", "Unit", "Location", "norm_Location", "Stock_Date", "Batch_No", "data_quality_warnings"
        ]
    else:
        display_cols = [
            "Stock_ID", "CAS_Number", "Product_Name", "Concentration",
            "Quantity", "Unit", "Location", "Stock_Date", "Batch_No"
        ]

    st.dataframe(filtered_df[display_cols], use_container_width=True, height=450)

# -----------------------------------------------------------------------------
# TAB 3: LOW STOCK DASHBOARD
# -----------------------------------------------------------------------------
with tab_low_stock:
    st.markdown("### 📉 Low Stock & Inventory Level Dashboard")
    st.caption("Deterministic comparison of active stock against ERP Minimum Stock thresholds.")

    eval_data = low_stock_engine.evaluate_all_stock(by_location=True)

    c_mode = st.radio(
        "Select Evaluation Scope:",
        ["Facility-Specific (Hyderabad & Bangalore)", "Company-Wide Aggregate"],
        horizontal=True
    )

    if c_mode == "Company-Wide Aggregate":
        df_cw = pd.DataFrame(eval_data["company_wide"])
        st.dataframe(
            df_cw[[
                "cas_number", "product_name", "concentration",
                "available_stock", "minimum_stock", "shortage", "unit", "status"
            ]],
            use_container_width=True
        )
    else:
        col_hyd, col_blr = st.columns(2)
        with col_hyd:
            st.markdown("#### 🏢 **Hyderabad Facility**")
            df_hyd = pd.DataFrame(eval_data["by_location"]["Hyderabad"])
            st.dataframe(
                df_hyd[[
                    "cas_number", "product_name", "concentration",
                    "available_stock", "minimum_stock", "shortage", "unit", "status"
                ]],
                use_container_width=True,
                height=500
            )

        with col_blr:
            st.markdown("#### 🏢 **Bangalore Facility**")
            df_blr = pd.DataFrame(eval_data["by_location"]["Bangalore"])
            st.dataframe(
                df_blr[[
                    "cas_number", "product_name", "concentration",
                    "available_stock", "minimum_stock", "shortage", "unit", "status"
                ]],
                use_container_width=True,
                height=500
            )

# -----------------------------------------------------------------------------
# TAB 4: DATA QUALITY REPORT
# -----------------------------------------------------------------------------
with tab_quality:
    st.markdown("### 📋 Data Quality Audit Report")
    st.caption("Comprehensive log of raw data inconsistencies, spelling variants, negative quantities, and unclassified products.")

    dq_df = loader.get_data_quality_df()

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Total Issues Logged", len(dq_df))
    q2.metric("Spelling Variations", len(dq_df[dq_df["issue_type"] == "Location Spelling Variation"]))
    q3.metric("Negative Quantities", len(dq_df[dq_df["issue_type"] == "Negative Quantity"]))
    q4.metric("Unknown / Non-Std", len(dq_df[dq_df["issue_type"].isin(["Unknown Product", "Non-Standard Location"])]))

    st.markdown("#### 🔎 **Audit Log Table**")
    issue_filter = st.multiselect("Filter by Issue Type", dq_df["issue_type"].unique().tolist(), default=dq_df["issue_type"].unique().tolist())
    st.dataframe(dq_df[dq_df["issue_type"].isin(issue_filter)], use_container_width=True, height=450)

# -----------------------------------------------------------------------------
# TAB 5: PURCHASE REQUIREMENTS
# -----------------------------------------------------------------------------
with tab_purchase:
    st.markdown("### 🛒 Purchase Requisitions & Replenishment")
    st.caption("Automated purchase requirements generated from facility shortage rules.")

    scope_sel = st.selectbox("Requisition Scope", ["Facility-Specific Replenishment", "Company-Wide Replenishment"])
    calc_scope = "location" if "Facility" in scope_sel else "company-wide"
    reqs = low_stock_engine.generate_purchase_requirements(evaluation_scope=calc_scope)
    reqs_df = pd.DataFrame([r.to_dict() for r in reqs])

    if not reqs_df.empty:
        st.dataframe(
            reqs_df[[
                "requirement_id", "scope", "cas_number", "product_name",
                "concentration", "available_stock", "minimum_stock",
                "shortage_quantity", "unit", "reason", "approval_status"
            ]],
            use_container_width=True,
            height=400
        )

        csv_data = reqs_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Purchase Requirements (CSV)",
            data=csv_data,
            file_name="symax_purchase_requirements.csv",
            mime="text/csv"
        )
    else:
        st.success("✅ No replenishment required! All active inventory levels are above minimum thresholds.")
