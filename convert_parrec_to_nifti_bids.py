#!/usr/bin/env python3
"""
BIDS-compatible conversion of Philips PAR/REC files to NIfTI format.

This script processes all PAR/REC files and converts them to BIDS-compliant
NIfTI files with comprehensive JSON sidecar files containing metadata from
PAR and XML files.
"""

import os
import json
import subprocess
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

def parse_par_file(par_file_path):
    metadata = {}
    with open(par_file_path, 'r') as f:
        content = f.read()
    lines = content.split('\n')
    for line in lines:
        if ':' in line and line.strip().startswith('.'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip().replace('.', '').strip()
                value = parts[1].strip()
                metadata[key] = value
    scan_params = {}
    for line in lines:
        if 'Repetition time [ms]' in line:
            scan_params['RepetitionTime'] = float(line.split(':')[1].strip())
        elif 'Echo time [ms]' in line:
            scan_params['EchoTime'] = float(line.split(':')[1].strip())
        elif 'FOV (ap,fh,rl) [mm]' in line:
            fov_str = line.split(':')[1].strip()
            fov_values = [float(x) for x in fov_str.split()]
            scan_params['FieldOfView'] = fov_values
        elif 'Scan resolution  (x, y)' in line:
            res_str = line.split(':')[1].strip()
            res_values = [int(x) for x in res_str.split()]
            scan_params['ScanResolution'] = res_values
        elif 'Technique' in line:
            scan_params['Technique'] = line.split(':')[1].strip()
        elif 'Patient position' in line:
            scan_params['PatientPosition'] = line.split(':')[1].strip()
        elif 'Angulation midslice(ap,fh,rl)[degr]' in line:
            ang_str = line.split(':')[1].strip()
            ang_values = [float(x) for x in ang_str.split()]
            scan_params['Angulation'] = ang_values
        elif 'Off Centre midslice(ap,fh,rl) [mm]' in line:
            off_str = line.split(':')[1].strip()
            off_values = [float(x) for x in off_str.split()]
            scan_params['OffCentre'] = off_values
    metadata['ScanParameters'] = scan_params
    return metadata

def parse_xml_file(xml_file_path):
    metadata = {}
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        series_info = root.find('.//Series_Info')
        if series_info is not None:
            for attr in series_info.findall('.//Attribute'):
                name = attr.get('Name', '')
                value = attr.text
                if name and value:
                    metadata[name] = value
        image_info = root.find('.//Image_Info')
        if image_info is not None:
            for attr in image_info.findall('.//Attribute'):
                name = attr.get('Name', '')
                value = attr.text
                if name and value:
                    metadata[f"Image_{name}"] = value
    except Exception as e:
        print(f"Warning: Could not parse XML file {xml_file_path}: {e}")
    return metadata

def extract_scan_info_from_filename(filename):
    match = re.match(r'(.+?)_(\d+)_(\d+)_(\d+)_(\d+\.\d+\.\d+)_\((.+?)\)\.PAR', filename)
    if match:
        patient_id, exam_num, series_num, acquisition_num, time, protocol = match.groups()
        return {
            'patient_id': patient_id,
            'exam_number': exam_num,
            'series_number': series_num,
            'acquisition_number': acquisition_num,
            'time': time,
            'protocol_name': protocol,
            'series_description': protocol
        }
    return {}

def bids_entities(scan_info):
    sub = re.sub(r'[^a-zA-Z0-9]', '', scan_info.get('patient_id', 'unknown'))
    ses = scan_info.get('series_number', '01')
    acq = scan_info.get('protocol_name', 'acq')
    acq = re.sub(r'[^a-zA-Z0-9]', '', acq.lower())
    protocol = scan_info.get('protocol_name', '').lower()
    if 't1w' in protocol or 't1' in protocol:
        suffix = 'T1w'
        modality = 'anat'
    elif 't2w' in protocol or 't2' in protocol:
        suffix = 'T2w'
        modality = 'anat'
    elif 'funct' in protocol or 'resting' in protocol:
        suffix = 'bold'
        modality = 'func'
        task = 'rest'
    elif 'anticipation' in protocol:
        suffix = 'bold'
        modality = 'func'
        task = 'anticipation'
        run = protocol.split('anticipation')[-1] if 'anticipation' in protocol else '01'
    elif 'test_epi' in protocol:
        suffix = 'bold'
        modality = 'func'
        task = 'test'
    elif 'b0map' in protocol:
        suffix = 'phasediff'
        modality = 'fmap'
    elif 'survey' in protocol:
        suffix = 'scout'
        modality = 'anat'
    else:
        suffix = 'unknown'
        modality = 'unknown'
    parts = [f"sub-{sub}"]
    if ses != '01':
        parts.append(f"ses-{ses}")
    parts.append(f"acq-{acq}")
    if modality == 'func' and 'task' in locals():
        parts.append(f"task-{task}")
    if 'run' in locals():
        parts.append(f"run-{run}")
    parts.append(suffix)
    return '_'.join(parts), modality

def convert_parrec_to_nifti(par_file, output_dir):
    par_path = Path(par_file)
    base_name = par_path.stem
    output_file = output_dir / f"{base_name}.nii"
    cmd = [
        'parrec2nii',
        '--overwrite',
        '--output-dir', str(output_dir),
        '--compressed',
        '--store-header',
        str(par_file)
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"Error converting {par_file}: {e}\nstderr: {e.stderr}")
        return None

def main():
    input_dir = Path("XMLPARREC")
    output_dir = Path("NIfTI_BIDS")
    output_dir.mkdir(exist_ok=True)
    par_files = list(input_dir.glob("*.PAR"))
    if not par_files:
        print("No PAR files found in XMLPARREC directory")
        return
    print(f"Found {len(par_files)} PAR files to convert")
    for par_file in par_files:
        print(f"\nProcessing: {par_file.name}")
        scan_info = extract_scan_info_from_filename(par_file.name)
        scan_info['source_files'] = [
            str(par_file),
            str(par_file.with_suffix('.REC')),
            str(par_file.with_suffix('.XML')),
            str(par_file.with_suffix('.V41'))
        ]
        bids_base, modality = bids_entities(scan_info)
        par_metadata = parse_par_file(par_file)
        xml_file = par_file.with_suffix('.XML')
        xml_metadata = parse_xml_file(xml_file) if xml_file.exists() else {}
        nifti_file = convert_parrec_to_nifti(par_file, output_dir)
        actual_nifti_file = None
        if nifti_file and nifti_file.exists():
            actual_nifti_file = nifti_file
        else:
            gz_file = Path(str(nifti_file) + '.gz')
            if gz_file.exists():
                actual_nifti_file = gz_file
        if actual_nifti_file and actual_nifti_file.exists():
            # Rename to BIDS
            # Always use .nii.gz for compressed NIfTI
            bids_nifti = output_dir / f"{bids_base}.nii.gz"
            actual_nifti_file.rename(bids_nifti)
            # JSON sidecar
            json_data = {
                "ConversionSoftware": "convert_parrec_to_nifti_bids.py",
                "ConversionSoftwareVersion": "2.0",
                "ConversionDate": datetime.now().isoformat(),
                "SourceFormat": "Philips PAR/REC",
                "SourceFiles": scan_info['source_files'],
                "BIDSModality": modality,
                **par_metadata,
                "XMLMetadata": xml_metadata
            }
            json_file = bids_nifti.with_suffix('.json')
            with open(json_file, 'w') as f:
                json.dump(json_data, f, indent=2)
            print(f"BIDS conversion complete: {bids_nifti.name} + {json_file.name}")
        else:
            print(f"Failed to convert {par_file.name}")
    print(f"\nBIDS conversion complete! Files saved in: {output_dir}")

if __name__ == "__main__":
    main() 