import streamlit as st
import pandas as pd
import requests
from typing import List, Optional

# Configure Streamlit
st.set_page_config(page_title="RxNorm Drug Search", page_icon="💊", layout="wide")
st.title("💊 RxNorm Drug Search")
st.markdown("Search clinically relevant drug information using the NLM's RxNorm API.")
st.markdown("---")

# Map TTY codes to human-readable clinical terms
TERM_TYPE_MAP = {
    "IN": "Ingredient",
    "BN": "Brand Name",
    "SCD": "Clinical Drug",
    "SBD": "Branded Drug",
    "PSN": "Prescribable Name",
    "SY": "Synonym"
}

# --- API Calls ---

def get_rxcui_for_ingredient(term: str) -> Optional[str]:
    url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={term}&maxEntries=1"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        c = r.json().get('approximateGroup', {}).get('candidate', [])
        return c[0]['rxcui'] if c else None
    except:
        return None

def call_endpoint(url: str, source: str) -> List[dict]:
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        items = r.json().get('drugGroup' if 'drugs.json' in url else 'relatedGroup', {})
        groups = items.get('conceptGroup', [])
        data = []
        for g in groups:
            for c in g.get('conceptProperties', []):
                if c.get('suppress', '') not in ['N', '']:
                    continue
                data.append({
                    'rxcui': c['rxcui'],
                    'name': c.get('name') or c.get('synonym'),
                    'termType': TERM_TYPE_MAP.get(c.get('tty', ''), c.get('tty')),
                    'source': source
                })
        return data
    except:
        return []

def get_autocomplete_options(partial: str) -> List[str]:
    url = f"https://rxnav.nlm.nih.gov/REST/spellingsuggestions.json?name={partial}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        suggestions = r.json().get('suggestionGroup', {}).get('suggestionList', {}).get('suggestion', [])
        return suggestions if suggestions else [partial]
    except:
        return [partial]

@st.cache_data(ttl=3600)
def search_rxnorm_api(term: str) -> pd.DataFrame:
    term = term.strip()
    results = []

    # 1. /drugs.json
    base_url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={term}"
    results += call_endpoint(base_url, 'direct')

    # 2. Ingredient-based lookup
    rxcui = get_rxcui_for_ingredient(term)
    if rxcui:
        related_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=BN+SBD+SCD"
        results += call_endpoint(related_url, 'related')

    df = pd.DataFrame(results).drop_duplicates('rxcui')
    df = df[df['name'].notna()]
    df = df.sort_values('name').reset_index(drop=True)
    return df

# --- UI Section ---

# Initialize session
if "search_trigger" not in st.session_state:
    st.session_state["search_trigger"] = False

col1, col2 = st.columns([3, 1])

with col1:
    partial_term = st.text_input("Enter drug name (ingredient or brand):", placeholder="e.g. acetaminophen, ibuprofen, omeprazole")
    suggestions = get_autocomplete_options(partial_term) if len(partial_term) >= 3 else []
    selected_term = st.selectbox("Suggested options:", suggestions) if suggestions else partial_term

with col2:
    st.markdown("")
    st.markdown("")
    if st.button("🔍 Search"):
        st.session_state["search_trigger"] = True

# Perform search
if st.session_state.get("search_trigger", False) and selected_term and len(selected_term.strip()) >= 2:
    with st.spinner(f"Searching for '{selected_term}'..."):
        df = search_rxnorm_api(selected_term)
    st.session_state["search_trigger"] = False

    if not df.empty:
        st.success(f"Found {len(df)} results for '{selected_term}':")
        st.dataframe(
            df.rename(columns={
                "name": "Drug Name",
                "termType": "Term Type",
                "source": "Source",
                "rxcui": "RxCUI"
            }),
            use_container_width=True
        )
        # Optional CSV download
        st.download_button(
            label="📥 Download Results as CSV",
            data=df.to_csv(index=False),
            file_name=f"rxnorm_{selected_term.replace(' ', '_')}.csv",
            mime="text/csv"
        )
    else:
        st.warning(f"No results found for '{selected_term}'.")
elif not selected_term or len(selected_term.strip()) < 2:
    st.info("Enter at least 2 characters to search.")
