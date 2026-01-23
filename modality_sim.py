import sys
import os
import time
import random  # Import modul untuk acak/random
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE, StoragePresentationContexts
from pynetdicom.sop_class import ModalityWorklistInformationFind

# 1. Matikan Validasi Ketat
pydicom.config.settings.reading_validation_mode = pydicom.config.IGNORE
pydicom.config.settings.writing_validation_mode = pydicom.config.IGNORE

# --- KONFIGURASI ---
ORTHANC_IP = '127.0.0.1'
ORTHANC_PORT = 4242
MY_AE_TITLE = 'FINDSCU'
ORTHANC_AE_TITLE = 'ORTHANC'

# Folder tempat file 1.DCM s/d 5.DCM berada
SOURCE_FOLDER = 'dummy'
INSTITUTION_NAME = "RS SIMULASI INDONESIA"

def query_worklist():
    print(f"\n[1] Menghubungi RIS/Orthanc ({ORTHANC_IP}:{ORTHANC_PORT})...")
    ae = AE(ae_title=MY_AE_TITLE)
    ae.add_requested_context(ModalityWorklistInformationFind)
    assoc = ae.associate(ORTHANC_IP, ORTHANC_PORT, ae_title=ORTHANC_AE_TITLE)

    if assoc.is_established:
        ds = Dataset()
        ds.PatientName = ''
        ds.PatientID = ''
        ds.AccessionNumber = ''
        ds.PatientBirthDate = ''
        ds.PatientSex = ''
        ds.StudyInstanceUID = ''
        ds.RequestedProcedureDescription = ''

        sps_seq = Dataset()
        sps_seq.Modality = ''
        sps_seq.ScheduledStationAETitle = ''
        sps_seq.ScheduledProcedureStepStartDate = ''

        ds.ScheduledProcedureStepSequence = [sps_seq]

        responses = assoc.send_c_find(ds, ModalityWorklistInformationFind)
        worklist_items = []
        for (status, identifier) in responses:
            if status and identifier:
                worklist_items.append(identifier)
        assoc.release()
        return worklist_items
    else:
        print("❌ Gagal connect ke Orthanc.")
        return []

def pick_random_and_send(patient_data):
    print(f"\n[2] Memilih file acak dari folder '{SOURCE_FOLDER}'...")

    # Cek Folder
    if not os.path.exists(SOURCE_FOLDER):
        print(f"❌ ERROR: Folder '{SOURCE_FOLDER}' tidak ditemukan!")
        return

    # Ambil daftar file (abaikan file sistem seperti .DS_Store)
    files = [f for f in os.listdir(SOURCE_FOLDER) if not f.startswith('.')]

    if len(files) == 0:
        print("❌ Folder kosong! Masukkan file 1.DCM dll ke dalamnya.")
        return

    # --- LOGIC RANDOM PICKER ---
    selected_filename = random.choice(files)
    filepath = os.path.join(SOURCE_FOLDER, selected_filename)
    print(f"    🎲 Terpilih file: {selected_filename}")

    try:
        # Baca File Terpilih
        ds = pydicom.dcmread(filepath, force=True)

        # --- AMBIL DATA DARI WORKLIST ---
        acc_num = patient_data.get('AccessionNumber', '')
        pat_name = str(patient_data.get('PatientName', 'No Name')).replace('^', ' ')
        pat_id = patient_data.get('PatientID', '')
        pat_birth = patient_data.get('PatientBirthDate', '')
        pat_sex = patient_data.get('PatientSex', '')
        study_desc = patient_data.get('RequestedProcedureDescription', 'Pemeriksaan Radiologi')
        study_uid = patient_data.get('StudyInstanceUID', generate_uid())

        if 'ScheduledProcedureStepSequence' in patient_data:
            modality = patient_data.ScheduledProcedureStepSequence[0].get('Modality', 'OT')
        else:
            modality = 'OT'

        # --- INJECT IDENTITAS BARU ---
        ds.PatientName = pat_name
        ds.PatientID = pat_id
        ds.PatientBirthDate = pat_birth
        ds.PatientSex = pat_sex
        ds.AccessionNumber = acc_num
        ds.StudyID = acc_num
        ds.StudyDescription = study_desc
        ds.InstitutionName = INSTITUTION_NAME

        ds.StudyInstanceUID = study_uid
        ds.Modality = modality

        # Generate UID Baru agar unik (PENTING!)
        ds.SeriesInstanceUID = generate_uid()
        ds.SOPInstanceUID = generate_uid()
        if hasattr(ds, 'file_meta'):
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

        ds.SeriesDescription = f"Simulasi {modality} (Source: {selected_filename})"
        ds.SeriesNumber = 1
        ds.InstanceNumber = 1

        # Update Tanggal
        dt = time.strftime("%Y%m%d")
        tm = time.strftime("%H%M%S")
        ds.StudyDate = dt
        ds.ContentDate = dt

        # --- KIRIM KE PACS ---
        print("\n[3] Mengirim Hasil ke PACS...")
        ae = AE(ae_title=MY_AE_TITLE)
        ae.requested_contexts = StoragePresentationContexts

        assoc = ae.associate(ORTHANC_IP, ORTHANC_PORT, ae_title=ORTHANC_AE_TITLE)
        if assoc.is_established:
            status = assoc.send_c_store(ds)
            if status and status.Status == 0x0000:
                print(f"✅ SUKSES! Gambar terkirim untuk pasien: {pat_name}")
            else:
                print(f"❌ Gagal kirim. Status: {status}")
            assoc.release()
        else:
            print("❌ Gagal connect ke Orthanc.")

    except Exception as e:
        print(f"❌ Error saat memproses file: {e}")

def main():
    while True:
        print("\n" + "="*40)
        print("   SIMULATOR V5 (RANDOM PICKER)")
        print("="*40)

        items = query_worklist()

        if not items:
            print("📭 Tidak ada Worklist.")
            choice = input("\n[Enter] Refresh | [q] Keluar: ")
            if choice.lower() == 'q': break
            continue

        print(f"\n📋 Ditemukan {len(items)} Pasien:")
        print(f"{'No':<4} {'Accession #':<18} {'Modality':<5} {'Patient Name'}")
        print("-" * 60)

        for i, item in enumerate(items):
            try:
                pname = str(item.get('PatientName', '-')).replace('^', ' ')
                acc = item.get('AccessionNumber', '-')
                mod = '-'
                if 'ScheduledProcedureStepSequence' in item:
                     mod = item.ScheduledProcedureStepSequence[0].get('Modality', '-')
                print(f"{i+1:<4} {acc:<18} {mod:<5} {pname}")
            except:
                pass

        print("-" * 60)
        choice = input("Pilih nomor pasien (atau 'q' keluar): ")

        if choice.lower() == 'q': break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                pick_random_and_send(items[idx])
                input("\n[Enter] Kembali ke menu...")
        except ValueError:
            pass

if __name__ == "__main__":
    main()