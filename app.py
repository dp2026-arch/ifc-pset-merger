import streamlit as st
import ifcopenshell
import tempfile
import os

st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️")
st.title("F+P Architekten 🏗️IFC Pset Zusammenführung")
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
UBE_Pset_Specific_Window"""

sources_input = st.text_area(
    label="Zu suchende Psets (eines pro Zeile):", 
    value=default_sources, 
    height=250
)

sources_to_merge = [line.strip() for line in sources_input.split('\n') if line.strip()]

st.divider()
# --------------------------------------

uploaded_file = st.file_uploader("Wählen Sie eine IFC-Datei aus", type=['ifc'])

if uploaded_file is not None:
    if st.button("Psets verarbeiten", type="primary"): # 'type="primary"' macht den Button farbig hervorgehoben
        
        if not sources_to_merge:
            st.error("Bitte geben Sie mindestens ein Quell-Pset in das Textfeld ein.")
        elif not target_name.strip():
            st.error("Bitte geben Sie einen gültigen Ziel-Namen ein.")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_in:
                tmp_in.write(uploaded_file.getvalue())
                temp_in_path = tmp_in.name

            try:
                ifc_file = ifcopenshell.open(temp_in_path)
                
                # --- NEU: Vorbereitung für Statistik und Fortschritt ---
                all_objects = ifc_file.by_type("IfcObject")
                total_objects = len(all_objects)
                
                modified_objects_count = 0
                removed_psets_count = 0
                
                # UI-Elemente für den Fortschritt (werden im Loop aktualisiert)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # --- LOGIK ---
                for i, obj in enumerate(all_objects):
                    
                    # Update der UI (wir machen das nicht bei jedem einzelnen Bauteil, 
                    # da das den Browser verlangsamt, sondern ca. in 5%-Schritten)
                    if total_objects > 0 and i % max(1, (total_objects // 20)) == 0:
                        progress = int((i / total_objects) * 100)
                        progress_bar.progress(progress)
                        status_text.text(f"⏳ Verarbeite Bauteil {i} von {total_objects}...")

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
                                removed_psets_count += 1 # Zähler erhöhen
                            
                        main_pset.HasProperties = all_properties
                        modified_objects_count += 1 # Zähler erhöhen
                        
                    elif len(matching_psets) == 1:
                        main_rel, main_pset = matching_psets[0]
                        main_pset.Name = target_name
                        modified_objects_count += 1 # Zähler erhöhen
                
                # Fortschritt auf 100% setzen
                progress_bar.progress(100)
                status_text.text("✅ Verarbeitung abgeschlossen!")
                # --- ENDE DER LOGIK ---

                # Datei speichern
                temp_out_path = temp_in_path.replace(".ifc", "_processed.ifc")
                ifc_file.write(temp_out_path)
                
                # --- NEU: Statistik anzeigen ---
                st.success("Die IFC-Datei wurde erfolgreich bereinigt!")
                
                # st.columns erstellt ein Raster für ein schickes Dashboard-Gefühl
                col1, col2, col3 = st.columns(3)
                col1.metric("Untersuchte Bauteile", f"{total_objects:,}")
                col2.metric("Angepasste Bauteile", f"{modified_objects_count:,}")
                col3.metric("Gelöschte (leere) Psets", f"{removed_psets_count:,}")

                st.divider()

                with open(temp_out_path, "rb") as file:
                    st.download_button(
                        label="⬇️ Bereinigte IFC-Datei herunterladen",
                        data=file,
                        file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
                        mime="application/octet-stream",
                        type="primary"
                    )

            except Exception as e:
                st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

            finally:
                if os.path.exists(temp_in_path):
                    os.remove(temp_in_path)