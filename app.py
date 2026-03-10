import streamlit as st
import ifcopenshell
import tempfile
import os

# 1. Seiten-Konfiguration
st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️")
st.title("🏗️ IFC Pset Zusammenführung")
st.write("Laden Sie eine IFC-Datei hoch und definieren Sie flexibel, welche Psets zusammengeführt werden sollen.")

# --- NEU: Einstellungs-Bereich (UI) ---
st.subheader("⚙️ Parameter einstellen")

# A) Textfeld für den Ziel-Namen
target_name = st.text_input(
    label="Name des neuen Ziel-Psets:", 
    value="UBA_Pset_Specific",
    help="Geben Sie hier den Namen ein, den das zusammengeführte Pset am Ende erhalten soll."
)

# B) Textbereich für die Quell-Psets (Standardwerte voreingetragen)
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
UBE_Pset_Specific_Window"""

sources_input = st.text_area(
    label="Zu suchende Psets (eines pro Zeile):", 
    value=default_sources, 
    height=250,
    help="Kopieren Sie hier alle Psets hinein, die gesucht und zusammengeführt werden sollen. Jede Zeile wird als ein Pset-Name gewertet."
)

# Die mehrzeilige Eingabe in eine saubere Python-Liste umwandeln (leere Zeilen ignorieren)
sources_to_merge = [line.strip() for line in sources_input.split('\n') if line.strip()]

st.divider() # Eine optische Trennlinie
# --------------------------------------

# 2. Datei-Upload-Widget
uploaded_file = st.file_uploader("Wählen Sie eine IFC-Datei aus", type=['ifc'])

if uploaded_file is not None:
    st.info("Datei erfolgreich hochgeladen. Klicken Sie auf 'Verarbeiten', um zu starten.")
    
    # Button zum Starten
    if st.button("Psets verarbeiten"):
        
        # Sicherstellen, dass auch Psets eingegeben wurden
        if not sources_to_merge:
            st.error("Bitte geben Sie mindestens ein Quell-Pset in das Textfeld ein.")
        elif not target_name.strip():
            st.error("Bitte geben Sie einen gültigen Ziel-Namen ein.")
        else:
            with st.spinner('Verarbeite IFC-Datei... Das kann einen Moment dauern.'):
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_in:
                    tmp_in.write(uploaded_file.getvalue())
                    temp_in_path = tmp_in.name

                try:
                    ifc_file = ifcopenshell.open(temp_in_path)
                    
                    # --- HIER STARTET DIE LOGIK ---
                    # Wir durchsuchen alle Objekte im Modell
                    for obj in ifc_file.by_type("IfcObject"):
                        matching_psets = []
                        
                        for rel in getattr(obj, "IsDefinedBy", []):
                            if rel.is_a("IfcRelDefinesByProperties"):
                                pset = rel.RelatingPropertyDefinition
                                if pset and pset.is_a("IfcPropertySet") and getattr(pset, "Name", None) in sources_to_merge:
                                    matching_psets.append((rel, pset))
                        
                        if len(matching_psets) > 1:
                            main_rel, main_pset = matching_psets[0]
                            main_pset.Name = target_name
                            
                            all_properties = list(main_pset.HasProperties) if getattr(main_pset, "HasProperties", None) else []
                            existing_prop_names = {p.Name for p in all_properties}
                            
                            for rel, other_pset in matching_psets[1:]:
                                if getattr(other_pset, "HasProperties", None):
                                    for prop in other_pset.HasProperties:
                                        if prop.Name not in existing_prop_names:
                                            all_properties.append(prop)
                                            existing_prop_names.add(prop.Name)
                                
                                ifc_file.remove(rel)
                                inverse_rel = getattr(other_pset, "Defines", None) or getattr(other_pset, "PropertyDefinitionOf", [])
                                if not inverse_rel:
                                    ifc_file.remove(other_pset)
                                
                            main_pset.HasProperties = all_properties
                            
                        elif len(matching_psets) == 1:
                            main_rel, main_pset = matching_psets[0]
                            main_pset.Name = target_name
                    # --- HIER ENDET DIE LOGIK ---

                    temp_out_path = temp_in_path.replace(".ifc", "_processed.ifc")
                    ifc_file.write(temp_out_path)
                    
                    st.success(f"Erfolg! Die Psets wurden zusammengeführt und in '{target_name}' umbenannt.")

                    with open(temp_out_path, "rb") as file:
                        st.download_button(
                            label="⬇️ Bereinigte IFC-Datei herunterladen",
                            data=file,
                            file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
                            mime="application/octet-stream"
                        )

                except Exception as e:
                    st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

                finally:
                    if os.path.exists(temp_in_path):
                        os.remove(temp_in_path)