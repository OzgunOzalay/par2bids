#!/usr/bin/env python3
"""
BIDS-compatible conversion of Philips PAR/REC files to NIfTI format.

This script processes all PAR/REC files and converts them to BIDS-compliant
NIfTI files with comprehensive JSON sidecar files containing metadata from
PAR and XML files.

Directory structure:
Data/
├── [SubjectID]/
│   ├── XMLPARREC/          # Input directory
│   │   ├── *.PAR           # Parameter files
│   │   ├── *.REC           # Raw image data
│   │   ├── *.XML           # Extended metadata
│   │   └── *.V41           # Additional parameters
│   └── NIfTI_BIDS/         # Output directory
│       ├── sub-*_ses-*_task-*_bold.nii.gz
│       ├── sub-*_ses-*_task-*_bold.json
│       └── ...

Usage:
    python convert_parrec_to_nifti_bids.py                    # Convert all subjects
    python convert_parrec_to_nifti_bids.py VA003             # Convert specific subject
    python convert_parrec_to_nifti_bids.py VA003 VA004       # Convert multiple subjects
"""

import os
import json
import subprocess
import re
import xml.etree.ElementTree as ET
import argparse
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
    # Use subject ID from the parent folder name
    sub = scan_info.get('subject_id', 'unknown')
    
    # Clean up acquisition name - remove "wip", "vip" and redundant information
    acq = scan_info.get('protocol_name', 'acq')
    acq = re.sub(r'[^a-zA-Z0-9]', '', acq.lower())
    acq = acq.replace('wip', '').replace('vip', '')  # Remove wip/vip
    acq = acq.replace('_', '').strip()  # Remove underscores and whitespace
    
    protocol = scan_info.get('protocol_name', '').lower()
    
    # Determine modality and suffix based on protocol
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
    
    # Build BIDS filename - no session information, no acquisition labels
    parts = [f"sub-{sub}"]
    
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

def process_subject_directory(subject_dir):
    """Process a single subject directory."""
    subject_id = subject_dir.name
    xmlparrec_dir = subject_dir / "XMLPARREC"
    nifti_bids_dir = subject_dir / "NIfTI_BIDS"
    
    if not xmlparrec_dir.exists():
        print(f"No XMLPARREC directory found in {subject_dir}")
        return
    
    # Create output directory
    nifti_bids_dir.mkdir(exist_ok=True)
    
    # Find all PAR files
    par_files = list(xmlparrec_dir.glob("*.PAR"))
    
    if not par_files:
        print(f"No PAR files found in {xmlparrec_dir}")
        return
    
    print(f"\nProcessing subject {subject_id}: Found {len(par_files)} PAR files")
    
    # Process each PAR file
    for par_file in par_files:
        print(f"\nProcessing: {par_file.name}")
        
        # Extract scan information
        scan_info = extract_scan_info_from_filename(par_file.name)
        scan_info['subject_id'] = subject_id  # Add subject ID from parent folder
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
        nifti_file = convert_parrec_to_nifti(par_file, nifti_bids_dir)
        
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
            bids_nifti = nifti_bids_dir / f"{bids_base}.nii.gz"
            actual_nifti_file.rename(bids_nifti)
            
            # JSON sidecar
            json_data = {
                "ConversionSoftware": "convert_parrec_to_nifti_bids.py",
                "ConversionSoftwareVersion": "2.0",
                "ConversionDate": datetime.now().isoformat(),
                "SourceFormat": "Philips PAR/REC",
                "SourceFiles": scan_info['source_files'],
                "BIDSModality": modality,
                "SubjectID": subject_id,
                **par_metadata,
                "XMLMetadata": xml_metadata
            }
            json_file = bids_nifti.with_suffix('.json')
            with open(json_file, 'w') as f:
                json.dump(json_data, f, indent=2)
            print(f"BIDS conversion complete: {bids_nifti.name} + {json_file.name}")
        else:
            print(f"Failed to convert {par_file.name}")

def main():
    """Main conversion function."""
    parser = argparse.ArgumentParser(
        description="Convert Philips PAR/REC files to BIDS-compliant NIfTI format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Convert all subjects
  %(prog)s VA003             # Convert specific subject
  %(prog)s VA003 VA004       # Convert multiple subjects
        """
    )
    parser.add_argument(
        'subjects', 
        nargs='*', 
        help='Specific subject IDs to convert (e.g., VA003 VA004). If none provided, converts all subjects.'
    )
    parser.add_argument(
        '--data-dir', 
        default='Data', 
        help='Base data directory (default: Data)'
    )
    parser.add_argument(
        '--verbose', '-v', 
        action='store_true', 
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    
    if not data_dir.exists():
        print(f"Data directory '{data_dir}' not found. Please ensure your data is organized as:")
        print(f"{data_dir}/")
        print("├── [SubjectID]/")
        print("│   ├── XMLPARREC/")
        print("│   │   ├── *.PAR")
        print("│   │   ├── *.REC")
        print("│   │   ├── *.XML")
        print("│   │   └── *.V41")
        print("│   └── NIfTI_BIDS/ (will be created)")
        return
    
    # Find all subject directories
    all_subject_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    
    if not all_subject_dirs:
        print(f"No subject directories found in {data_dir}/")
        return
    
    # Filter subjects if specific ones were requested
    if args.subjects:
        requested_subjects = set(args.subjects)
        subject_dirs = [d for d in all_subject_dirs if d.name in requested_subjects]
        
        # Check for missing subjects
        found_subjects = {d.name for d in subject_dirs}
        missing_subjects = requested_subjects - found_subjects
        if missing_subjects:
            print(f"Warning: The following requested subjects were not found: {missing_subjects}")
            print(f"Available subjects: {[d.name for d in all_subject_dirs]}")
        
        if not subject_dirs:
            print("No requested subjects found. Available subjects:")
            for d in all_subject_dirs:
                print(f"  - {d.name}")
            return
    else:
        subject_dirs = all_subject_dirs
    
    print(f"Found {len(subject_dirs)} subject(s) to process:")
    for subject_dir in subject_dirs:
        print(f"  - {subject_dir.name}")
    
    # Process each subject
    for subject_dir in subject_dirs:
        print(f"\n{'='*50}")
        print(f"Processing subject: {subject_dir.name}")
        print(f"{'='*50}")
        process_subject_directory(subject_dir)
    
    print(f"\nBIDS conversion complete for {len(subject_dirs)} subject(s)!")

if __name__ == "__main__":
    main() 