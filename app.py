import streamlit as st
import ifcopenshell
import ifcopenshell.guid  # Wichtig für die Generierung neuer IFC-IDs
import tempfile
import os
import base64

# --- Funktion zum Laden des Logos ---
def get_image_as_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# --- Seitenkonfiguration ---
st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️")

# --- Titel mit eigenem Logo ---
try:
    # WICHTIG: Ersetzen Sie "image_1.png" durch den exakten Namen Ihrer Bilddatei!
    logo_base64 = get_image_as_base64("image_1.png")
    
    st.markdown(
        f"""
        <h1 style="display: flex; align-items: center; gap: 10px;">
            <img src="data:image/png;base64,{logo_base64}" width="90" style="border-radius: 10px;"> 
            IFC Pset Zusammenführung
        </h1>
        """,
        unsafe_allow_html=True
    )
except FileNotFoundError:
    st.title("F+P Architekten🏗️ IFC Pset Zusammenführung")
    st.warning("⚠️ Logo-Bild ('image_1.png') wurde nicht gefunden. Bitte legen Sie es in denselben Ordner wie das Skript.")

st.write("Laden Sie eine IFC-Datei hoch und definieren Sie flexibel, welche Psets zusammengeführt werden sollen.")

# --- Einstellungs-Bereich (UI) ---
st.subheader("⚙️ Parameter einstellen")

target_name = st.text_input(
    label="Name des neuen Ziel-Psets:", 
    value="UBA_Pset_Specific"
)

default_sources = """UBE_Pset_Specific_Beam
UBE_Pset_Specific_BuildingElementProxy
UBE_Pset_Specific_Column
UBE_Pset_Specific_CoveringCeiling
UBE_Pset_Specific_CoveringFlooring
UBE_Pset_Specific_CoveringWall
UBE_Pset_Specific_CurtainWall
UBE_Pset_Specific_Door
UBE_Pset_Specific_Furniture
UBE_Pset_Specific_Member
UBE_Pset_Specific_PipeSegment
UBE_Pset_Specific_Railing
UBE_Pset_Specific_Roof
UBE_PSet_Specific_Schlitz und Durchbruch
UBE_Pset_Specific_ShadingDevice
UBE_Pset_Specific_Slab
UBE_Pset_Specific_Space
UBE_PSet_Specific_Stairs
UBE_Pset_Specific_Wall
UBE_Pset_Specific_Window
Pset_WallCommon"""

sources_input = st.text_area(
    label="Zu suchende Psets (eines pro Zeile):", 
    value=default_sources, 
    height=250
)

sources_to_merge = [line.strip() for line in sources_input.split('\n') if line.strip()]

st.divider()
# --------------------------------------

uploaded_file = st.file_uploader("Wählen Sie eine IFC-Datei aus", type=['ifc'])

# --- Session State Initialisierung für den Streamlit-Lifecycle ---
if 'processed_file' not in st.session_state:
    st.session_state.processed_file = None
if 'stats' not in st.session_state:
    st.session_state.stats = None

if uploaded_file is not None:
    if st.button("Psets verarbeiten", type="primary"): 
        
        if not sources_to_merge:
            st.error("Bitte geben Sie mindestens ein Quell-Pset in das Textfeld ein.")
        elif not target_name.strip():
            st.error("Bitte geben Sie einen gültigen Ziel-Namen ein.")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_in:
                tmp_in.write(uploaded_file.getvalue())
                temp_in_path = tmp_in.name
                temp_out_path = temp_in_path.replace(".ifc", "_processed.ifc")

            try:
                ifc_file = ifcopenshell.open(temp_in_path)
                
                all_objects = ifc_file.by_type("IfcObject")
                total_objects = len(all_objects)
                
                modified_objects_count = 0
                removed_psets_count = 0
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # OwnerHistory einmalig holen (wird für neue Psets benötigt)
                owner_history_list = ifc_file.by_type("IfcOwnerHistory")
                owner_history = owner_history_list[0] if owner_history_list else None
                
                # --- LOGIK ---
                for i, obj in enumerate(all_objects):
                    
                    if total_objects > 0 and i % max(1, (total_objects // 20)) == 0:
                        progress = min(100, int((i / total_objects) * 100))
                        progress_bar.progress(progress)
                        status_text.text(f"⏳ Verarbeite Bauteil {i} von {total_objects}...")

                    # --- FAST-TRACK ---
                    is_defined_by = getattr(obj, "IsDefinedBy", [])
                    if not is_defined_by:
                        continue 

                    matching_psets = []
                    
                    for rel in is_defined_by:
                        if rel.is_a("IfcRelDefinesByProperties"):
                            pset = rel.RelatingPropertyDefinition
                            if pset and pset.is_a("IfcPropertySet") and getattr(pset, "Name", None) in sources_to_merge:
                                matching_psets.append((rel, pset))
                    
                    if matching_psets: 
                        # 1. Alle Eigenschaften aus den gefundenen Psets sammeln
                        all_properties = []
                        existing_prop_names = set()
                        
                        for rel, pset in matching_psets:
                            if getattr(pset, "HasProperties", None):
                                for prop in pset.HasProperties:
                                    if prop.Name not in existing_prop_names:
                                        all_properties.append(prop)
                                        existing_prop_names.add(prop.Name)
                        
                        # 2. Neues Ziel-Pset erstellen (sofern Eigenschaften existieren)
                        if all_properties:
                            new_pset = ifc_file.createIfcPropertySet(
                                GlobalId=ifcopenshell.guid.new(),
                                OwnerHistory=owner_history,
                                Name=target_name,
                                Description=None,
                                HasProperties=all_properties
                            )
                            
                            # 3. Neues Pset mit dem aktuellen Bauteil verknüpfen
                            ifc_file.createIfcRelDefinesByProperties(
                                GlobalId=ifcopenshell.guid.new(),
                                OwnerHistory=owner_history,
                                Name=None,
                                Description=None,
                                RelatedObjects=[obj],
                                RelatingPropertyDefinition=new_pset
                            )
                            
                            modified_objects_count += 1 
                            
                            # 4. Alte Psets sicher auflösen (Shared Pset Logik)
                            for rel, pset in matching_psets:
                                related_objects = list(rel.RelatedObjects)
                                if obj in related_objects:
                                    related_objects.remove(obj)
                                
                                if len(related_objects) == 0:
                                    ifc_file.remove(rel)
                                    
                                    # Prüfen ob das Pset noch von anderen Relationen genutzt wird
                                    inverse_rel = getattr(pset, "Defines", None) or getattr(pset, "PropertyDefinitionOf", [])
                                    if not inverse_rel:
                                        ifc_file.remove(pset)
                                        removed_psets_count += 1 
                                else:
                                    rel.RelatedObjects = related_objects

                progress_bar.progress(100)
                status_text.text("✅ Verarbeitung abgeschlossen!")

                # Datei speichern
                ifc_file.write(temp_out_path)

                # Datei in den RAM laden für den Session State
                with open(temp_out_path, "rb") as file:
                    st.session_state.processed_file = file.read()
                    
                st.session_state.stats = {
                    "total": total_objects,
                    "modified": modified_objects_count,
                    "removed": removed_psets_count
                }

            except Exception as e:
                st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

            finally:
                if 'temp_in_path' in locals() and os.path.exists(temp_in_path):
                    os.remove(temp_in_path)
                if 'temp_out_path' in locals() and os.path.exists(temp_out_path):
                    os.remove(temp_out_path)

# --- Download-Bereich außerhalb der Button-Logik ---
if st.session_state.processed_file is not None:
    st.success("Die IFC-Datei wurde erfolgreich bereinigt!")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Untersuchte Bauteile", f"{st.session_state.stats['total']:,}")
    col2.metric("Angepasste Bauteile", f"{st.session_state.stats['modified']:,}")
    col3.metric("Gelöschte (leere) Psets", f"{st.session_state.stats['removed']:,}")

    st.divider()

    st.download_button(
        label="⬇️ Bereinigte IFC-Datei herunterladen",
        data=st.session_state.processed_file,
        file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
        mime="application/octet-stream",
        type="primary"
    )