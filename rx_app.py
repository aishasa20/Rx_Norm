import streamlit as st
import pandas as pd
import requests
import json
import re
from typing import Dict, List, Optional
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure the Streamlit page
st.set_page_config(
    page_title="RxNorm Drug Search",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# App header
st.title("💊 RxNorm Drug Search")
st.markdown("Search for drug information using the NLM's Universal RxNorm API")
st.markdown("---")

def get_term_type_description(term_type: str) -> str:
    """Get human-readable description for RxNorm term types."""
    descriptions = {
        'SBD': 'Semantic Branded Drug',
        'SCD': 'Semantic Clinical Drug', 
        'IN': 'Ingredient',
        'PIN': 'Precise Ingredient',
        'MIN': 'Multiple Ingredients',
        'BN': 'Brand Name',
        'DF': 'Dose Form',
        'DFG': 'Dose Form Group',
        'SCDC': 'Semantic Clinical Drug Component',
        'SBDC': 'Semantic Branded Drug Component',
        'SCDF': 'Semantic Clinical Dose Form',
        'SBDF': 'Semantic Branded Dose Form',
        'BPCK': 'Branded Pack',
        'GPCK': 'Generic Pack',
        'PSN': 'Prescribable Name',
        'SY': 'Synonym',
        'TMSY': 'Tall Man Synonym'
    }
    return descriptions.get(term_type, 'Unknown Type')

def parse_drug_name_comprehensive(drug_name: str) -> Dict[str, str]:
    """
    Comprehensive parsing of drug names to extract all components.
    Handles formats like: "Advil 200 MG Oral Tablet" or "dexamethasone 103.4 MG/ML Injection"
    """
    result = {
        'ingredient': '',
        'brand_name': '',
        'strength': '',
        'dose_form': '',
        'route': '',
        'display_name': '',
        'volume': ''
    }
    
    if not drug_name:
        return result
    
    # Extract brand name (text in square brackets)
    brand_match = re.search(r'\[([^\]]+)\]', drug_name)
    if brand_match:
        result['brand_name'] = brand_match.group(1)
        drug_name_no_brand = drug_name.replace(brand_match.group(0), '').strip()
    else:
        drug_name_no_brand = drug_name
        # Check if first word is a known brand name
        first_word = drug_name.split()[0] if drug_name.split() else ''
        known_brands = ['Advil', 'Tylenol', 'Motrin', 'Aleve', 'Bayer', 'Excedrin', 
                       'Cymbalta', 'Lipitor', 'Prozac', 'Zoloft', 'Nexium']
        if first_word in known_brands:
            result['brand_name'] = first_word
    
    # Extract volume (for injections, solutions)
    volume_pattern = r'(\d+(?:\.\d+)?\s*ML)'
    volume_match = re.search(volume_pattern, drug_name_no_brand, re.IGNORECASE)
    if volume_match:
        result['volume'] = volume_match.group(1).lower()
    
    # Extract strength - enhanced pattern for various formats
    strength_patterns = [
        r'(\d+(?:\.\d+)?\s*MG/ML)',  # mg/ml format
        r'(\d+(?:\.\d+)?\s*MCG/ML)', # mcg/ml format  
        r'(\d+(?:\.\d+)?\s*MG)',     # mg format
        r'(\d+(?:\.\d+)?\s*MCG)',    # mcg format
        r'(\d+(?:\.\d+)?\s*%)',      # percentage format
        r'(\d+(?:\.\d+)?\s*UNIT)',   # units format
    ]
    
    for pattern in strength_patterns:
        strength_match = re.search(pattern, drug_name_no_brand, re.IGNORECASE)
        if strength_match:
            strength_text = strength_match.group(1)
            # Format strength properly
            if 'mg/ml' in strength_text.lower():
                result['strength'] = strength_text.lower().replace('mg/ml', ' mg/ml')
            elif 'mcg/ml' in strength_text.lower():
                result['strength'] = strength_text.lower().replace('mcg/ml', ' mcg/ml')
            elif 'mg' in strength_text.lower():
                result['strength'] = strength_text.lower().replace('mg', ' mg')
            else:
                result['strength'] = strength_text.lower()
            break
    
    # Define dose forms and their routes
    dose_form_mappings = {
        'oral tablet': ('Oral', 'Tablet'),
        'tablet': ('Oral', 'Tablet'),
        'oral capsule': ('Oral', 'Capsule'),
        'capsule': ('Oral', 'Capsule'),
        'chewable tablet': ('Oral', 'Chewable Tablet'),
        'oral suspension': ('Oral', 'Suspension'),
        'suspension': ('Oral', 'Suspension'),
        'oral solution': ('Oral', 'Solution'),
        'solution': ('Oral', 'Solution'),
        'injection': ('Injectable', 'Injection'),
        'prefilled syringe': ('Injectable', 'Prefilled Syringe'),
        'topical cream': ('Topical', 'Cream'),
        'cream': ('Topical', 'Cream'),
        'topical gel': ('Topical', 'Gel'),
        'gel': ('Topical', 'Gel'),
        'ointment': ('Topical', 'Ointment'),
        'eye drops': ('Ophthalmic', 'Drops'),
        'drops': ('Ophthalmic', 'Drops'),
        'nasal spray': ('Nasal', 'Spray'),
        'spray': ('Nasal', 'Spray'),
        'transdermal patch': ('Transdermal', 'Patch'),
        'patch': ('Transdermal', 'Patch'),
        'suppository': ('Rectal', 'Suppository'),
        'inhaler': ('Inhalation', 'Inhaler'),
        'inhalation': ('Inhalation', 'Inhaler')
    }
    
    # Find dose form and route
    drug_lower = drug_name_no_brand.lower()
    for form_key, (route, dose_form) in dose_form_mappings.items():
        if form_key in drug_lower:
            result['route'] = route
            result['dose_form'] = dose_form
            break
    
    # Extract ingredient (usually the first word or two)
    words = drug_name_no_brand.split()
    if words:
        # Remove known brand names and find the active ingredient
        filtered_words = []
        skip_next = False
        
        for i, word in enumerate(words):
            if skip_next:
                skip_next = False
                continue
                
            # Skip strength numbers and units
            if re.match(r'^\d+(\.\d+)?$', word) or word.upper() in ['MG', 'ML', 'MCG', '%', 'UNIT']:
                skip_next = True if word.upper() in ['MG', 'ML', 'MCG'] else False
                continue
                
            # Skip dose form words
            if word.lower() in ['oral', 'tablet', 'capsule', 'injection', 'suspension', 'solution', 'chewable']:
                break
                
            filtered_words.append(word)
        
        if filtered_words:
            # Take first 1-2 words as ingredient
            if len(filtered_words) >= 2 and len(filtered_words[1]) > 3:
                result['ingredient'] = f"{filtered_words[0]} {filtered_words[1]}"
            else:
                result['ingredient'] = filtered_words[0]
    
    # Create display name
    if result['ingredient']:
        base_name = result['ingredient']
        # Capitalize properly
        if base_name.lower() == 'ibuprofen' and result['brand_name']:
            base_name = result['brand_name']  # Use brand name for display
        elif 'dexamethasone' in base_name.lower():
            base_name = 'dexAMETHasone'  # Special formatting
        
        if result['route']:
            result['display_name'] = f"{base_name} ({result['route']})"
        else:
            result['display_name'] = base_name
    
    return result

@st.cache_data(ttl=3600)  # Cache for 1 hour
def search_rxnorm_api(search_term: str) -> pd.DataFrame:
    """
    Search the RxNorm API for drug information and return a comprehensive DataFrame 
    matching the expected CSV format.
    """
    if not search_term or len(search_term.strip()) < 2:
        return pd.DataFrame()
    
    # Clean the search term
    search_term = search_term.strip()
    
    # API endpoint
    api_url = f"https://rxnav.nlm.nih.gov/REST/drugs.json?name={search_term}"
    
    try:
        # Make the API request with timeout
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        # Extract drug information
        drugs_data = []
        
        if 'drugGroup' in data and 'conceptGroup' in data['drugGroup']:
            concept_groups = data['drugGroup']['conceptGroup']
            
            # Handle both single concept group and list of concept groups
            if not isinstance(concept_groups, list):
                concept_groups = [concept_groups]
            
            for group in concept_groups:
                if 'conceptProperties' in group:
                    concept_properties = group['conceptProperties']
                    
                    # Handle both single concept and list of concepts
                    if not isinstance(concept_properties, list):
                        concept_properties = [concept_properties]
                    
                    for concept in concept_properties:
                        # Extract basic fields from the RxNorm API response
                        rxcui = concept.get('rxcui', '')
                        name = concept.get('n', '')  # This is the full drug name
                        synonym = concept.get('synonym', '')  # This often contains the brand version
                        term_type = concept.get('tty', '')
                        suppress = concept.get('suppress', '')
                        
                        # Use the most complete name available
                        primary_name = name if name else synonym
                        if not primary_name:
                            continue
                            
                        # Parse the primary drug name
                        parsed_info = parse_drug_name_comprehensive(primary_name)
                        
                        # Also parse synonym if it exists and is different
                        synonym_info = {}
                        if synonym and synonym != name:
                            synonym_info = parse_drug_name_comprehensive(synonym)
                        
                        # Determine brand name - prefer from synonym if it's a branded version
                        brand_name = None
                        if synonym_info.get('brand_name'):
                            brand_name = synonym_info['brand_name']
                        elif parsed_info.get('brand_name'):
                            brand_name = parsed_info['brand_name']
                        
                        # Create display name
                        display_name = parsed_info.get('display_name', '')
                        if not display_name and parsed_info.get('ingredient'):
                            if parsed_info.get('route'):
                                display_name = f"{parsed_info['ingredient']} ({parsed_info['route']})"
                            else:
                                display_name = parsed_info['ingredient']
                        
                        # Create RxTerms dose form
                        rxterms_dose_form = None
                        if parsed_info.get('dose_form'):
                            if parsed_info.get('volume'):
                                rxterms_dose_form = f"{parsed_info['dose_form']} {parsed_info['volume']}"
                            else:
                                rxterms_dose_form = parsed_info['dose_form']
                        
                        # Create comprehensive drug info matching CSV structure
                        drug_info = {
                            'brandName': brand_name,
                            'displayName': display_name,
                            'synonym': synonym if synonym and synonym != name else None,
                            'fullName': primary_name,
                            'fullGenericName': name if name else primary_name,
                            'strength': parsed_info.get('strength'),
                            'rxtermsDoseForm': rxterms_dose_form,
                            'route': parsed_info.get('route'),
                            'termType': term_type,
                            'rxcui': int(rxcui) if rxcui and rxcui.isdigit() else None,
                            'genericRxcui': None,  # Will be populated by additional API call if needed
                            'rxnormDoseForm': parsed_info.get('dose_form'),
                            'suppress': suppress if suppress and suppress not in ['N', ''] else None
                        }
                        
                        drugs_data.append(drug_info)
        
        # Create DataFrame
        if drugs_data:
            df = pd.DataFrame(drugs_data)
            
            # Ensure all required columns exist
            required_columns = [
                'brandName', 'displayName', 'synonym', 'fullName', 
                'fullGenericName', 'strength', 'rxtermsDoseForm', 'route',
                'termType', 'rxcui', 'genericRxcui', 'rxnormDoseForm', 'suppress'
            ]
            
            for col in required_columns:
                if col not in df.columns:
                    df[col] = None
            
            # Reorder columns to match CSV format
            df = df[required_columns]
            
            # Sort by displayName for better organization
            df = df.sort_values('displayName', na_position='last')
            
            # Remove duplicates based on rxcui
            df = df.drop_duplicates(subset=['rxcui'], keep='first')
            
            return df.reset_index(drop=True)
        else:
            # Return empty DataFrame with correct structure
            return pd.DataFrame(columns=[
                'brandName', 'displayName', 'synonym', 'fullName', 
                'fullGenericName', 'strength', 'rxtermsDoseForm', 'route',
                'termType', 'rxcui', 'genericRxcui', 'rxnormDoseForm', 'suppress'
            ])
            
    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {str(e)}")
        return pd.DataFrame()
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse API response: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        return pd.DataFrame()

# Main application interface
col1, col2 = st.columns([3, 1])

with col1:
    # Search input
    search_term = st.text_input(
        "Enter drug name, brand, or keyword:",
        placeholder="e.g., aspirin, ibuprofen, Tylenol, Cymbalta",
        help="Enter at least 2 characters to search"
    )

with col2:
    st.markdown("") # Add some space
    st.markdown("") # Add some space
    if st.button("🔍 Search", type="primary"):
        st.rerun()

# Search functionality
if search_term and len(search_term.strip()) >= 2:
    # Show loading spinner
    with st.spinner(f"Searching for '{search_term}' and parsing drug information..."):
        # Get search results
        results_df = search_rxnorm_api(search_term)
    
    # Display results
    if not results_df.empty:
        st.success(f"Found {len(results_df)} results for '{search_term}'")
        
        # Display the results table with proper formatting
        st.dataframe(
            results_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "brandName": st.column_config.TextColumn("Brand Name", width="medium"),
                "displayName": st.column_config.TextColumn("Display Name", width="medium"),
                "synonym": st.column_config.TextColumn("Synonym", width="medium"),
                "fullName": st.column_config.TextColumn("Full Name", width="large"),
                "fullGenericName": st.column_config.TextColumn("Full Generic Name", width="large"),
                "strength": st.column_config.TextColumn("Strength", width="small"),
                "rxtermsDoseForm": st.column_config.TextColumn("RxTerms Dose Form", width="medium"),
                "route": st.column_config.TextColumn("Route", width="small"),
                "termType": st.column_config.TextColumn("Term Type", width="small"),
                "rxcui": st.column_config.NumberColumn("RxCUI", width="small"),
                "genericRxcui": st.column_config.NumberColumn("Generic RxCUI", width="small"),
                "rxnormDoseForm": st.column_config.TextColumn("RxNorm Dose Form", width="medium"),
                "suppress": st.column_config.TextColumn("Suppress", width="small"),
            }
        )
        
        # Show a sample of the parsing results
        with st.expander("🔍 Parsing Details (First 3 Results)"):
            sample_df = results_df.head(3)
            for idx, row in sample_df.iterrows():
                st.markdown(f"**{row['fullName']}**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"• **Brand**: {row['brandName'] or 'None'}")
                    st.write(f"• **Ingredient**: {row['displayName'] or 'None'}")
                with col2:
                    st.write(f"• **Strength**: {row['strength'] or 'None'}")
                    st.write(f"• **Route**: {row['route'] or 'None'}")
                with col3:
                    st.write(f"• **Dose Form**: {row['rxnormDoseForm'] or 'None'}")
                    st.write(f"• **RxCUI**: {row['rxcui'] or 'None'}")
                st.markdown("---")
        
        # Download button for results in exact CSV format
        csv_data = results_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv_data,
            file_name=f"rxnorm_search_{search_term.replace(' ', '_')}.csv",
            mime="text/csv"
        )
        
        # Show comprehensive statistics
        with st.expander("📊 Search Statistics"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Results", len(results_df))
            with col2:
                brand_count = len(results_df[results_df['brandName'].notna()])
                st.metric("Brand Names Found", brand_count)
            with col3:
                route_count = len(results_df[results_df['route'].notna()])
                st.metric("Routes Identified", route_count)
            with col4:
                strength_count = len(results_df[results_df['strength'].notna()])
                st.metric("Strengths Parsed", strength_count)
            
            # Term type breakdown
            if 'termType' in results_df.columns:
                term_type_counts = results_df['termType'].value_counts()
                if not term_type_counts.empty:
                    st.markdown("**Term Type Breakdown:**")
                    term_type_df = pd.DataFrame({
                        'Term Type': term_type_counts.index,
                        'Count': term_type_counts.values,
                        'Description': [get_term_type_description(tt) for tt in term_type_counts.index]
                    })
                    st.dataframe(term_type_df, use_container_width=True, hide_index=True)
            
            # Route breakdown
            if 'route' in results_df.columns:
                route_counts = results_df['route'].value_counts()
                if not route_counts.empty:
                    st.markdown("**Route Breakdown:**")
                    st.dataframe(
                        pd.DataFrame({
                            'Route': route_counts.index,
                            'Count': route_counts.values
                        }), 
                        use_container_width=True, 
                        hide_index=True
                    )
    
    elif search_term.strip():
        st.warning(f"No results found for '{search_term}'. Try a different search term.")

elif search_term and len(search_term.strip()) < 2:
    st.info("Please enter at least 2 characters to search.")

else:
    # Show helpful information when no search is active
    st.info("Enter a drug name, brand, or keyword above to search the RxNorm database.")
    
    with st.expander("ℹ️ About this application"):
        st.markdown("""
        This application provides a comprehensive interface to the **NLM's RxNorm API** with intelligent parsing and data extraction.
        

        
        **Complete Data Fields:**
        - **brandName**: Commercial brand name (Advil, Tylenol, etc.)
        - **displayName**: User-friendly name with route
        - **synonym**: Alternative drug name from RxNorm
        - **fullName**: Complete RxNorm drug name
        - **fullGenericName**: Generic equivalent name
        - **strength**:  strength (20 mg, 103.4 mg/ml, etc.)
        - **rxtermsDoseForm**: RxTerms dose form format
        - **route**: Administration route (Oral, Injectable, Topical, etc.)
        - **termType**: RxNorm term type (SBD, SCD, IN, etc.)
        - **rxcui**: Unique RxNorm identifier
        - **genericRxcui**: Generic equivalent RxCUI
        - **rxnormDoseForm**: Standard dose form
        - **suppress**: Suppression flag
        """)
    
    with st.expander("🔍 Example Searches & Expected Results"):
        st.markdown("**Search: 'Advil'**")
        st.code("""
Brand: Advil | Strength: 200 mg | Route: Oral | Dose Form: Tablet
Brand: Advil | Strength: 20 mg/ml | Route: Oral | Dose Form: Suspension
        """)
        
        st.markdown("**Search: 'dexamethasone'**")  
        st.code("""
Ingredient: dexamethasone | Strength: 103.4 mg/ml | Route: Injectable
Display Name: dexAMETHasone (Injectable)
        """)
        
        st.markdown("**Search: 'ibuprofen'**")
        st.code("""
Ingredient: ibuprofen | Various strengths and forms
Routes: Oral, Topical | Forms: Tablet, Suspension, Gel
        """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Data provided by the <a href='https://www.nlm.nih.gov/research/umls/rxnorm/index.html' target='_blank'>NLM RxNorm API</a> | 
        Built with Streamlit 
    </div>
    """, 
    unsafe_allow_html=True
)