import streamlit as st
import ifcopenshell
import ifcopenshell.api  # <-- NEU: Wir nutzen jetzt die API wie in Blender!
import tempfile
import os
import base64

# --- Funktion zum Laden des Logos ---
def get_image_as_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️")

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
    st.title("F+P Architekten🏗️ IFC Pset Zusammenführung")

st.write("Laden Sie eine IFC-Datei hoch und definieren Sie flexibel, welche Psets zusammengeführt werden sollen.")

st.subheader("⚙️ Parameter einstellen")
target_name = st.text_input("Name des neuen Ziel-Psets:", value="UBA_Pset_Specific")

default_sources = """UBE_Pset_Specific_Beam
UBE_Pset_Specific_BuildingElementProxy
UBE_Pset_Specific_Wall"""

sources_input = st.text_area("Zu suchende Psets (eines pro Zeile):", value=default_sources, height=250)
sources_to_merge = set([line.strip() for line in sources_input.split('\n') if line.strip()]) # als Set für schnellere Suche

st.divider()

uploaded_file = st.file_uploader("Wählen Sie eine IFC-Datei aus", type=['ifc'])

if 'processed_file' not in st.session_state:
    st.session_state.processed_file = None
if 'stats' not in st.session_state:
    st.session_state.stats = None

if uploaded_file is not None:
    if st.button("Psets verarbeiten", type="primary"): 
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
                # BLENDER-LOGIK STARTET HIER
                # ==========================================
                status_text.text("🔍 Schritt 1/3: Suche relevante Psets (Rückwärtssuche)...")
                relevant_psets = [p for p in ifc_file.by_type("IfcPropertySet") if getattr(p, "Name", None) in sources_to_merge]
                
                objects_to_update = {}

                # 1. DATEN SAMMELN
                for pset in relevant_psets:
                    rels = getattr(pset, "Defines", []) or getattr(pset, "PropertyDefinitionOf", [])
                    for rel in rels:
                        if rel.is_a("IfcRelDefinesByProperties"):
                            for obj in rel.RelatedObjects:
                                if obj not in objects_to_update:
                                    objects_to_update[obj] = {"props": {}}
                                
                                if getattr(pset, "HasProperties", None):
                                    for prop in pset.HasProperties:
                                        objects_to_update[obj]["props"][prop.Name] = prop
                
                total_objects = len(objects_to_update)
                
                # 2. NEUE PSETS ERSTELLEN
                processed_objects = 0
                for i, (obj, data) in enumerate(objects_to_update.items()):
                    if i % max(1, (total_objects // 20)) == 0:
                        progress_bar.progress(min(50 + int((i / total_objects) * 40), 90))
                        status_text.text(f"⏳ Schritt 2/3: Erstelle neue Psets ({i+1}/{total_objects})...")

                    if data["props"]:
                        # API nutzen wie in Blender!
                        new_pset = ifcopenshell.api.run("pset.add_pset", ifc_file, product=obj, name=target_name)
                        new_pset.HasProperties = list(data["props"].values())
                        processed_objects += 1

                # 3. BRUTE-FORCE BEREINIGUNG
                status_text.text("🧹 Schritt 3/3: Lösche alte Psets rigoros...")
                deleted_psets = set()
                for pset in relevant_psets:
                    rels = getattr(pset, "Defines", []) or getattr(pset, "PropertyDefinitionOf", [])
                    entities_to_delete.update(rels)  # Alle Relationen auf einmal hinzufügen
                    entities_to_delete.add(pset)  # Das Pset selbst hinzufügen
                total_deletes = len(entities_to_delete)
                deleted_psets = 0

                # Jetzt löschen wir alles in einer sauberen, iterativen Schleife
                for j, entity in enumerate(entities_to_delete):
                    # UI-Update nur alle 5% (spart extrem viel Render-Zeit in Streamlit)
                    if j % max(1, (total_deletes // 20)) == 0:
                        progress_bar.progress(min(100, int((j / total_deletes) * 100)))
                        status_text.text(f"🧹 Schritt 3/3: Lösche alte Daten ({j + 1} von {total_deletes})...")

                    try:
                        ifc_file.remove(entity)
                        if entity.is_a("IfcPropertySet"):
                            deleted_psets += 1
                    except Exception:
                        pass

                # ==========================================
                # BLENDER-LOGIK ENDE
                # ==========================================

                progress_bar.progress(100)
                status_text.text("✅ Verarbeitung erfolgreich abgeschlossen!")

                # Datei speichern
                ifc_file.write(temp_out_path)
                with open(temp_out_path, "rb") as file:
                    st.session_state.processed_file = file.read()
                    
                st.session_state.stats = {
                    "total": processed_objects,
                    "deleted": deleted_psets
                }

            except Exception as e:
                st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

            finally:
                if 'temp_in_path' in locals() and os.path.exists(temp_in_path):
                    os.remove(temp_in_path)
                if 'temp_out_path' in locals() and os.path.exists(temp_out_path):
                    os.remove(temp_out_path)

# --- Download-Bereich ---
if st.session_state.processed_file is not None and st.session_state.stats is not None:
    st.success("Die IFC-Datei wurde erfolgreich bereinigt!")
    
    col1, col2 = st.columns(2)
    col1.metric("Aktualisierte Bauteile", f"{st.session_state.stats['total']:,}")
    col2.metric("Gelöschte alte Psets", f"{st.session_state.stats['deleted']:,}")

    st.divider()

    st.download_button(
        label="⬇️ Bereinigte IFC-Datei herunterladen",
        data=st.session_state.processed_file,
        file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
        mime="application/octet-stream",
        type="primary"
    )