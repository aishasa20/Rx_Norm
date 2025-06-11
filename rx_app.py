import streamlit as st
import pandas as pd
import requests
import json
from typing import Dict, List, Optional

# Configure the Streamlit page
st.set_page_config(
    page_title="RxNorm Drug Search",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("💊 RxNorm Drug Search")
st.markdown("Search for drug information using the NLM's Universal RxNorm API")
st.markdown("---")

def get_term_type_description(term_type: str) -> str:
    descriptions = {
        'SBD': 'Semantic Branded Drug',
        'SCD': 'Semantic Clinical Drug', 
        'IN': 'Ingredient',
        'BN': 'Brand Name',
        'PSN': 'Prescribable Name',
        'SY': 'Synonym',
    }
    return descriptions.get(term_type, 'Unknown')

def get_rxcui_for_ingredient(term: str) -> Optional[str]:
    url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={term}&maxEntries=1"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        candidates = data.get('approximateGroup', {}).get('candidate', [])
        if candidates:
            return candidates[0].get('rxcui')
    except Exception:
        return None

def get_related_drugs_by_rxcui(rxcui: str) -> List[Dict]:
    url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=SBD+SCD+BN"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        results = []
        for group in data.get('relatedGroup', {}).get('conceptGroup', []):
            for concept in group.get('conceptProperties', []):
                results.append({
                    'rxcui': concept.get('rxcui'),
                    'name': concept.get('name'),
                    'termType': concept.get('tty'),
                    'suppress': concept.get('suppress', ''),
                    'source': 'related'
                })
        return results
    except Exception:
        return []

@st.cache_data(ttl=3600)
def search_rxnorm_api(search_term: str) -> pd.DataFrame:
    if not search_term or len(search_term.strip()) < 2:
        return pd.DataFrame()

    search_term = search_term.strip()
    drugs_data = []

    # Step 1: Direct search
    base_url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={search_term}"
    try:
        r = requests.get(base_url, timeout=5)
        r.raise_for_status()
        data = r.json()
        for group in data.get('drugGroup', {}).get('conceptGroup', []):
            for concept in group.get('conceptProperties', []):
                if concept.get('suppress', '') not in ['N', '']:
                    continue
                drugs_data.append({
                    'rxcui': concept.get('rxcui'),
                    'name': concept.get('name') or concept.get('synonym'),
                    'termType': concept.get('tty'),
                    'suppress': concept.get('suppress', ''),
                    'source': 'direct'
                })
    except Exception:
        st.warning("Failed to fetch primary results.")

    # Step 2: Related search via RxCUI
    rxcui = get_rxcui_for_ingredient(search_term)
    if rxcui:
        related = get_related_drugs_by_rxcui(rxcui)
        drugs_data.extend(related)

    # Step 3: Deduplicate and clean
    df = pd.DataFrame(drugs_data).drop_duplicates(subset='rxcui')
    df = df[df['name'].notna()]
    df = df.sort_values('name')
    return df.reset_index(drop=True)

# UI
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Enter drug name:", placeholder="e.g., acetaminophen, ibuprofen")
with col2:
    st.markdown("")
    st.markdown("")
    if st.button("🔍 Search", type="primary"):
        st.rerun()

if search_term and len(search_term.strip()) >= 2:
    with st.spinner(f"Searching for '{search_term}'..."):
        df = search_rxnorm_api(search_term)
    if not df.empty:
        st.success(f"Found {len(df)} results.")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No results found.")
else:
    st.info("Enter a drug name to begin search.")
