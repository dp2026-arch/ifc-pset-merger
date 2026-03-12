import streamlit as st
import ifcopenshell
import ifcopenshell.api
import tempfile
import os
import base64

# --- Funktion zum Laden des Logos ---
def get_image_as_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# --- Seitenkonfiguration ---
st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️", layout="centered")

try:
    logo_base64 = get_image_as_base64("image_1.png")
    st.markdown(
        f"""
        <h1 style="display: flex; align-items: center; gap: 10px;">
            <img src="data:image/png;base64,{logo_base64}" width="90" style="border-radius: 10px;"> 
            IFC Pset Zusammenführung
        </h1>
        """, unsafe_allow_html=True
    )
except FileNotFoundError:
    st.title("F+P Architekten 🏗️ IFC Pset Zusammenführung")

st.write("Laden Sie eine IFC-Datei hoch und definieren Sie flexibel, welche Psets in ein einzelnes Ziel-Pset zusammengeführt werden sollen.")

# --- Einstellungs-Bereich (UI) ---
st.subheader("⚙️ Parameter einstellen")
target_name = st.text_input("Name des neuen Ziel-Psets:", value="AWB_Specific")

default_sources = """UBE_Pset_Specific_Slab
UBE_Pset_Specific_Space
UBE_Pset_Specific_Stairs
UBE_Pset_Specific_Wall
UBE_Pset_Specific_Window"""

sources_input = st.text_area("Zu suchende Psets (eines pro Zeile):", value=default_sources, height=200)

# WICHTIG: Alle Eingaben in Kleinbuchstaben umwandeln für sichere Suche
sources_to_merge = set([line.strip().lower() for line in sources_input.split('\n') if line.strip()])

st.divider()

uploaded_file = st.file_uploader("Wählen Sie eine IFC-Datei aus", type=['ifc'])

# Session State initialisieren
if 'processed_file' not in st.session_state:
    st.session_state.processed_file = None
if 'stats' not in st.session_state:
    st.session_state.stats = None

if uploaded_file is not None:
    if st.button("🚀 Psets verarbeiten", type="primary"): 
        if not sources_to_merge:
            st.error("Bitte geben Sie mindestens ein Quell-Pset ein.")
        elif not target_name.strip():
            st.error("Bitte geben Sie einen gültigen Ziel-Namen ein.")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_in:
                tmp_in.write(uploaded_file.getvalue())
                temp_in_path = tmp_in.name
                temp_out_path = temp_in_path.replace(".ifc", "_processed.ifc")

            try:
                ifc_file = ifcopenshell.open(temp_in_path)
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # ==========================================
                # SCHRITT 1: DATEN SAMMELN (NEUE METHODE)
                # ==========================================
                status_text.text("🔍 Schritt 1/3: Suche relevante Psets (Rückwärtssuche)...")
                
                relevant_psets = [p for p in ifc_file.by_type("IfcPropertySet") if getattr(p, "Name", None) and p.Name.lower() in sources_to_merge]
                
                objects_to_update = {}
                collision_count = 0

                for pset in relevant_psets:
                    # KUGELSICHERE SUCHE: Findet alle Verknüpfungen (auch in IFC4 und an Typen)
                    inverses = ifc_file.get_inverse(pset)
                    
                    for inv in inverses:
                        related_objects = []
                        
                        # Fall 1: Reguläre Bauteile (Occurrences)
                        if inv.is_a("IfcRelDefinesByProperties"):
                            related_objects = getattr(inv, "RelatedObjects", [])
                        
                        # Fall 2: Typen in IFC4 (die hängen direkt am Pset)
                        elif inv.is_a("IfcTypeObject"):
                            related_objects = [inv]
                            
                        for obj in related_objects:
                            if obj not in objects_to_update:
                                objects_to_update[obj] = {"props": {}}
                            
                            if getattr(pset, "HasProperties", None):
                                for prop in pset.HasProperties:
                                    if prop.Name in objects_to_update[obj]["props"]:
                                        collision_count += 1
                                    objects_to_update[obj]["props"][prop.Name] = prop
                
                total_objects = len(objects_to_update)
                
                # ==========================================
                # SCHRITT 2: NEUE PSETS ERSTELLEN
                # ==========================================
                processed_objects = 0
                for i, (obj, data) in enumerate(objects_to_update.items()):
                    if total_objects > 0 and i % max(1, (total_objects // 20)) == 0:
                        progress_bar.progress(min(50 + int((i / total_objects) * 40), 90))
                        status_text.text(f"⏳ Schritt 2/3: Erstelle neue Psets ({i+1}/{total_objects})...")

                    if data["props"]:
                        new_pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=obj, name=target_name)
                        new_pset.HasProperties = list(data["props"].values())
                        processed_objects += 1

                # ==========================================
                # SCHRITT 3: BEREINIGUNG & GARBAGE COLLECTION
                # ==========================================
                status_text.text("🧹 Schritt 3/3: Sichere API-Bereinigung & Garbage Collection...")
                total_deletes = len(relevant_psets)
                deleted_psets = 0

                for j, pset in enumerate(relevant_psets):
                    if total_deletes > 0 and j % max(1, (total_deletes // 20)) == 0:
                        progress_bar.progress(min(100, int((j / total_deletes) * 100)))
                        status_text.text(f"🧹 Schritt 3/3: Lösche alte Psets ({j+1} von {total_deletes})...")
                    
                    inverses = ifc_file.get_inverse(pset)
                    
                    # 1. API-Bereinigung
                    for inv in inverses:
                        if inv.is_a("IfcRelDefinesByProperties"):
                            for obj in list(getattr(inv, "RelatedObjects", [])):
                                try:
                                    ifcopenshell.api.run("pset.remove_pset", ifc_file, product=obj, pset=pset)
                                except: pass
                        elif inv.is_a("IfcTypeObject"):
                            try:
                                ifcopenshell.api.run("pset.remove_pset", ifc_file, product=inv, pset=pset)
                            except: pass
                    
                    # 2. Harte Garbage Collection
                    try:
                        ifc_file.remove(pset)
                        deleted_psets += 1
                    except:
                        deleted_psets += 1

                progress_bar.progress(100)
                status_text.text("✅ Verarbeitung erfolgreich abgeschlossen!")

                # Datei speichern
                ifc_file.write(temp_out_path)
                with open(temp_out_path, "rb") as file:
                    st.session_state.processed_file = file.read()
                    
                st.session_state.stats = {
                    "total": processed_objects,
                    "deleted": deleted_psets,
                    "collisions": collision_count
                }

            except Exception as e:
                st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

            finally:
                if 'temp_in_path' in locals() and os.path.exists(temp_in_path):
                    try: os.remove(temp_in_path)
                    except: pass
                if 'temp_out_path' in locals() and os.path.exists(temp_out_path):
                    try: os.remove(temp_out_path)
                    except: pass

# --- Download-Bereich ---
if st.session_state.processed_file is not None and st.session_state.stats is not None:
    st.success("Die IFC-Datei wurde erfolgreich bereinigt!")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Aktualisierte Bauteile", f"{st.session_state.stats['total']:,}")
    col2.metric("Gelöschte alte Psets", f"{st.session_state.stats['deleted']:,}")
    
    coll = st.session_state.stats['collisions']
    col3.metric("Überschriebene Werte", f"{coll:,}", delta="- Kollisionen" if coll > 0 else "Keine", delta_color="inverse")

    st.divider()

    st.download_button(
        label="⬇️ Bereinigte IFC-Datei herunterladen",
        data=st.session_state.processed_file,
        file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
        mime="application/octet-stream",
        type="primary"
    )