import sys
import os
import time
import random
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE, build_context
from pynetdicom.sop_class import ModalityWorklistInformationFind

pydicom.config.settings.reading_validation_mode = pydicom.config.IGNORE
pydicom.config.settings.writing_validation_mode = pydicom.config.IGNORE

# --- KONFIGURASI ---
ORTHANC_IP = '127.0.0.1'
ORTHANC_PORT = 4242
ORTHANC_AE_TITLE = 'ORTHANC'
MY_AE_TITLE = 'FINDSCU'

SOURCE_FOLDER = 'dummy'
INSTITUTION_NAME = "RS SIMULASI"

def query_worklist():
    print(f"\nMenghubungi RIS/Orthanc ({ORTHANC_IP}:{ORTHANC_PORT})...")
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
        items = [identifier for (status, identifier) in responses if status and identifier]
        assoc.release()
        return items
    else:
        print("❌ Gagal connect ke Orthanc.")
        return []

def process_and_send(patient_data):
    if not os.path.exists(SOURCE_FOLDER):
        print(f"❌ ERROR: Folder '{SOURCE_FOLDER}' hilang!")
        return

    files = [f for f in os.listdir(SOURCE_FOLDER) if not f.startswith('.')]
    if len(files) == 0:
        print("❌ Folder kosong!")
        return

    selected_filename = random.choice(files)
    filepath = os.path.join(SOURCE_FOLDER, selected_filename)

    pat_name = str(patient_data.get('PatientName', 'No Name')).replace('^', ' ')

    try:
        # Baca File
        ds = pydicom.dcmread(filepath, force=True)

        # Deteksi Format Asli
        original_transfer_syntax = ds.file_meta.TransferSyntaxUID
        original_sop_class = ds.SOPClassUID

        # --- INJECT DATA BARU ---
        acc_num = patient_data.get('AccessionNumber', '')
        study_uid = patient_data.get('StudyInstanceUID', generate_uid())

        ds.PatientName = pat_name
        ds.PatientID = patient_data.get('PatientID', '')
        ds.PatientBirthDate = patient_data.get('PatientBirthDate', '')
        ds.PatientSex = patient_data.get('PatientSex', '')
        ds.AccessionNumber = acc_num
        ds.StudyID = acc_num
        ds.StudyDescription = patient_data.get('RequestedProcedureDescription', 'Radiology Exam')
        ds.InstitutionName = INSTITUTION_NAME
        ds.StudyInstanceUID = study_uid

        if 'ScheduledProcedureStepSequence' in patient_data:
            ds.Modality = patient_data.ScheduledProcedureStepSequence[0].get('Modality', 'OT')

        # Generate UID Baru
        ds.SeriesInstanceUID = generate_uid()
        ds.SOPInstanceUID = generate_uid()
        if hasattr(ds, 'file_meta'):
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

        ds.SeriesDescription = f"Simulasi {ds.Modality} (Source: {selected_filename})"

        # Update Tanggal
        dt = time.strftime("%Y%m%d")
        ds.StudyDate = dt
        ds.ContentDate = dt

        print("\nMengirim Hasil ke PACS...")

        ae = AE(ae_title=MY_AE_TITLE)
        context = build_context(original_sop_class, original_transfer_syntax)
        ae.add_requested_context(original_sop_class, original_transfer_syntax)

        assoc = ae.associate(ORTHANC_IP, ORTHANC_PORT, ae_title=ORTHANC_AE_TITLE)
        if assoc.is_established:
            status = assoc.send_c_store(ds)
            if status and status.Status == 0x0000:
                print(f"✅ SUKSES! Gambar JPEG/RAW terkirim untuk: {pat_name}")
            else:
                print(f"❌ Gagal kirim. Status: 0x{status.Status:04x}")
            assoc.release()
        else:
            print("❌ Gagal connect (Handshake Ditolak).")

    except Exception as e:
        print(f"❌ Error sistem: {e}")

def main():
    while True:
        print("\n" + "="*40)
        print("   SIMULATOR")
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
            except: pass

        print("-" * 60)
        choice = input("Pilih nomor pasien (atau 'q' keluar): ")

        if choice.lower() == 'q': break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                # Panggil fungsi clean
                process_and_send(items[idx])
                input("\n[Enter] Kembali ke menu...")
        except ValueError:
            pass

if __name__ == "__main__":
    main()