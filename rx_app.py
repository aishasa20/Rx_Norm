import streamlit as st
import pandas as pd
import requests
from typing import List, Optional

st.set_page_config(page_title="RxNorm Drug Search", page_icon="💊", layout="wide")

st.title("💊 RxNorm Drug Search")
st.markdown("Search drug info via NLM’s RxNorm API")
st.markdown("---")

def get_rxcui_for_ingredient(term: str) -> Optional[str]:
    url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={term}&maxEntries=1"
    try:
        r = requests.get(url, timeout=5); r.raise_for_status()
        c = r.json().get('approximateGroup', {}).get('candidate', [])
        return c[0]['rxcui'] if c else None
    except:
        return None

def call_endpoint(url: str, source: str) -> List[dict]:
    """Generic GET for RxNorm endpoints, extracting conceptProperties."""
    try:
        r = requests.get(url, timeout=5); r.raise_for_status()
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
                    'termType': c.get('tty'),
                    'source': source
                })
        return data
    except:
        return []

@st.cache_data(ttl=3600)
def search_rxnorm_api(term: str) -> pd.DataFrame:
    term = term.strip()
    results = []

    # 1. Run getDrugs (ingredient-based clinical & brand)
    rx_url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={term}"
    results += call_endpoint(rx_url, 'direct')

    # 2. Ingredient RxCUI → getDrugs by name again via that term for consistency
    rxcui = get_rxcui_for_ingredient(term)
    if rxcui:
        ingredient_url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={term}"
        results += call_endpoint(ingredient_url, 'ingredient')

    # 3. Ingredient RxCUI → branded & clinical via related.json
    if rxcui:
        url2 = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=BN+SBD+SCD"
        results += call_endpoint(url2, 'related')

    df = pd.DataFrame(results).drop_duplicates('rxcui')
    return df[df['name'].notna()].sort_values('name').reset_index(drop=True)

# UI
col1, col2 = st.columns([3,1])
with col1:
    q = st.text_input("Enter drug name:", placeholder="e.g. acetaminophen, ibuprofen")
with col2:
    if st.button("🔍 Search"):
        st.rerun()

if q and len(q.strip())>=2:
    with st.spinner(f"Searching '{q}'..."):
        df = search_rxnorm_api(q)
    if not df.empty:
        st.success(f"Found {len(df)} results:")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning(f"No results for '{q}'.")
else:
    st.info("Enter at least 2 characters to search.")
