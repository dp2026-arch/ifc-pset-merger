import streamlit as st
import ifcopenshell
import tempfile
import os
import base64  # <-- NEU: Wird für das Bild benötigt

# --- NEU: Funktion zum Laden des Logos ---
def get_image_as_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# --- Seitenkonfiguration ---
st.set_page_config(page_title="IFC Pset Merger", page_icon="🏗️")

# --- NEU: Titel mit eigenem Logo ---
# Wir nutzen try/except, damit die App nicht abstürzt, falls das Bild mal fehlt
try:
    # WICHTIG: Ersetzen Sie "image_1.png" durch den exakten Namen Ihrer Bilddatei!
    logo_base64 = get_image_as_base64("image_1.png")
    
    st.markdown(
        f"""
        <h1 style="display: flex; align-items: center; gap: 10px;">
            F+P Architekten 
            <img src="data:image/png;base64,{logo_base64}" width="90" style="border-radius: 8px;"> 
            IFC Pset Zusammenführung
        </h1>
        """,
        unsafe_allow_html=True
    )
except FileNotFoundError:
    # Fallback: Wenn das Bild nicht im Ordner liegt, zeigen wir das Standard-Emoji
    st.title("F+P Architekten 🏗️ IFC Pset Zusammenführung")
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
    if st.button("Psets verarbeiten", type="primary"): 
        
        if not sources_to_merge:
            st.error("Bitte geben Sie mindestens ein Quell-Pset in das Textfeld ein.")
        elif not target_name.strip():
            st.error("Bitte geben Sie einen gültigen Ziel-Namen ein.")
        else:
            # Temporäre Datei für den Input erstellen
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as tmp_in:
                tmp_in.write(uploaded_file.getvalue())
                temp_in_path = tmp_in.name
                temp_out_path = temp_in_path.replace(".ifc", "_processed.ifc")

            try:
                ifc_file = ifcopenshell.open(temp_in_path)
                
                # --- Vorbereitung für Statistik und Fortschritt ---
                all_objects = ifc_file.by_type("IfcObject")
                total_objects = len(all_objects)
                
                modified_objects_count = 0
                removed_psets_count = 0
                
                # UI-Elemente für den Fortschritt (werden im Loop aktualisiert)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # --- LOGIK ---
                for i, obj in enumerate(all_objects):
                    
                    # Update der UI in ca. 5%-Schritten, um den Browser nicht zu blockieren
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
                        # Mehrere Psets gefunden -> Zusammenführen
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
                                removed_psets_count += 1 
                        
                        main_pset.HasProperties = all_properties
                        modified_objects_count += 1 
                        
                    elif len(matching_psets) == 1:
                        # Nur ein Pset gefunden -> Nur umbenennen
                        main_rel, main_pset = matching_psets[0]
                        main_pset.Name = target_name
                        modified_objects_count += 1 
                
                # Fortschritt auf 100% setzen
                progress_bar.progress(100)
                status_text.text("✅ Verarbeitung abgeschlossen!")
                # --- ENDE DER LOGIK ---

                # Datei speichern
                ifc_file.write(temp_out_path)

                # --- Datei in den RAM laden und SOFORT von der Festplatte löschen ---
                with open(temp_out_path, "rb") as file:
                    processed_ifc_bytes = file.read()
                    
                # Reguläres Aufräumen nach dem Lesen in den RAM
                if os.path.exists(temp_in_path):
                    os.remove(temp_in_path)
                if os.path.exists(temp_out_path):
                    os.remove(temp_out_path)
                # -------------------------------------------------------------------------
                
                # --- Statistik anzeigen ---
                st.success("Die IFC-Datei wurde erfolgreich bereinigt!")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Untersuchte Bauteile", f"{total_objects:,}")
                col2.metric("Angepasste Bauteile", f"{modified_objects_count:,}")
                col3.metric("Gelöschte (leere) Psets", f"{removed_psets_count:,}")

                st.divider()

                # Download Button mit den Daten aus dem RAM
                st.download_button(
                    label="⬇️ Bereinigte IFC-Datei herunterladen",
                    data=processed_ifc_bytes,
                    file_name=f"{uploaded_file.name.replace('.ifc', '')}_bereinigt.ifc",
                    mime="application/octet-stream",
                    type="primary"
                )

            except Exception as e:
                st.error(f"Es gab einen Fehler bei der Verarbeitung: {e}")

            finally:
                # Fallback-Cleanup: Löscht die Dateien, falls das Skript vorzeitig durch einen Fehler abstürzt
                if 'temp_in_path' in locals() and os.path.exists(temp_in_path):
                    os.remove(temp_in_path)
                if 'temp_out_path' in locals() and os.path.exists(temp_out_path):
                    os.remove(temp_out_path)