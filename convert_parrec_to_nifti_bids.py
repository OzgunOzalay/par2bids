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
import shutil
from pathlib import Path
from datetime import datetime
import nibabel as nib



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

def bids_entities(scan_info, t1w_count=None):
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
        # Add run number for T1w files to distinguish multiple acquisitions
        if t1w_count is not None:
            if acq not in t1w_count:
                t1w_count[acq] = 1
            else:
                t1w_count[acq] += 1
            run = str(t1w_count[acq])
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
    
    # Build BIDS filename - no session information
    parts = [f"sub-{sub}"]
    
    # Add acquisition label for T1w files to distinguish different acquisitions
    if modality == 'anat' and 't1' in protocol:
        if acq and acq not in ['', 'none']:
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
    
    # Track T1w files to assign run numbers
    t1w_count = {}
    
    # Process each PAR file
    for par_file in par_files:
        print(f"\nProcessing: {par_file.name}")
        
        # Skip survey/coil files that cause conversion errors
        if 'survey' in par_file.name.lower() or 'coil' in par_file.name.lower():
            print(f"Skipping survey/coil file: {par_file.name}")
            continue
        
        # Extract scan information
        scan_info = extract_scan_info_from_filename(par_file.name)
        scan_info['subject_id'] = subject_id  # Add subject ID from parent folder
        scan_info['source_files'] = [
            str(par_file),
            str(par_file.with_suffix('.REC')),
            str(par_file.with_suffix('.XML')),
            str(par_file.with_suffix('.V41'))
        ]
        
        bids_base, modality = bids_entities(scan_info, t1w_count)
        par_metadata = extract_par_metadata(par_file)
        xml_file = par_file.with_suffix('.XML')
        xml_metadata = parse_xml_file(xml_file) if xml_file.exists() else {}
        
        # Special handling for fieldmaps
        if modality == 'fmap':
            # Extract magnitude data if available
            magnitude_file = extract_fieldmap_data(par_file, nifti_bids_dir, subject_id)
            # Convert the full fieldmap (will contain phase difference)
            nifti_file = convert_parrec_to_nifti(par_file, nifti_bids_dir)
        else:
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
            
            # Add BIDS-specific fields for fMRI runs
            if modality == 'func' and 'SliceTiming' in par_metadata:
                json_data.update({
                    "SliceEncodingDirection": "k",
                    "PhaseEncodingDirection": "j-",
                    "EffectiveEchoSpacing": 0.00051,  # Default for EPI, can be calculated from PAR if available
                    "EchoTrainLength": 1
                })
            
            # Add BIDS-specific fields for fieldmaps
            if modality == 'fmap':
                json_data.update({
                    "Units": "Hz",
                    "IntendedFor": []  # Will be populated by fMRIPrep
                })
            
            json_file = bids_nifti.with_suffix('.json')
            with open(json_file, 'w') as f:
                json.dump(json_data, f, indent=2)
            print(f"BIDS conversion complete: {bids_nifti.name} + {json_file.name}")
        else:
            print(f"Failed to convert {par_file.name}")

def extract_par_metadata(par_file):
    """Extract metadata from PAR file header"""
    metadata = {}
    
    with open(par_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Extract basic parameters
    tr_match = re.search(r'Repetition time \[ms\]\s*:\s*([\d.]+)', content)
    if tr_match:
        metadata['RepetitionTime'] = float(tr_match.group(1)) / 1000.0  # Convert to seconds
    
    te_match = re.search(r'Echo time \[ms\]\s*:\s*([\d.]+)', content)
    if te_match:
        metadata['EchoTime'] = float(te_match.group(1)) / 1000.0  # Convert to seconds
    
    slices_match = re.search(r'Max\. number of slices/locations\s*:\s*(\d+)', content)
    if slices_match:
        metadata['NumberOfSlices'] = int(slices_match.group(1))
    
    dynamics_match = re.search(r'Max\. number of dynamics\s*:\s*(\d+)', content)
    if dynamics_match:
        metadata['NumberOfDynamics'] = int(dynamics_match.group(1))
    
    fov_match = re.search(r'FOV \(ap,fh,rl\) \[mm\]\s*:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', content)
    if fov_match:
        metadata['FieldOfView'] = [float(fov_match.group(1)), float(fov_match.group(2)), float(fov_match.group(3))]
    
    resolution_match = re.search(r'Scan resolution\s*\(x, y\)\s*:\s*(\d+)\s+(\d+)', content)
    if resolution_match:
        metadata['ScanResolution'] = [int(resolution_match.group(1)), int(resolution_match.group(2))]
    
    # Extract slice timing for fMRI runs
    if metadata.get('NumberOfSlices') and metadata.get('RepetitionTime'):
        # Calculate slice timing for EPI sequences
        # For EPI, slice timing = (slice_number - 1) * (TR / number_of_slices)
        slice_timing = []
        for i in range(1, metadata['NumberOfSlices'] + 1):
            timing = (i - 1) * (metadata['RepetitionTime'] / metadata['NumberOfSlices'])
            slice_timing.append(timing)
        metadata['SliceTiming'] = slice_timing
    
    return metadata

def extract_fieldmap_data(par_file, output_dir, subject_id):
    """Extract magnitude and phase difference data from fieldmap PAR file using nibabel."""
    par_path = Path(par_file)
    base_name = par_path.stem
    
    # Read PAR file to understand structure
    with open(par_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Find the image information section
    lines = content.split('\n')
    image_lines = []
    in_image_section = False
    
    for line in lines:
        if '# === IMAGE INFORMATION ==========================================================' in line:
            in_image_section = True
            continue
        elif '# === END OF DATA DESCRIPTION FILE' in line:
            break
        elif in_image_section and line.strip() and not line.startswith('#'):
            # Skip header line
            if 'sl ec  dyn ph ty' not in line:
                image_lines.append(line.strip())
    
    # Parse image lines to separate magnitude and phase data
    magnitude_indices = []
    phase_indices = []
    
    for i, line in enumerate(image_lines):
        parts = line.split()
        if len(parts) >= 5:
            image_type = int(parts[4])  # 5th column is image_type_mr
            if image_type == 0:  # Magnitude (Philips uses 0 for magnitude)
                magnitude_indices.append(i)
            elif image_type == 18:  # Phase difference
                phase_indices.append(i)
    
    print(f"Found {len(magnitude_indices)} magnitude images and {len(phase_indices)} phase difference images")
    
    # Convert full PAR/REC to NIfTI
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
        full_nii = output_dir / f"{base_name}.nii.gz"
        bids_magnitude = output_dir / f"sub-{subject_id}_magnitude1.nii.gz"
        if full_nii.exists() and len(magnitude_indices) > 0:
            # Use nibabel to extract the first N volumes (magnitude images)
            img = nib.load(str(full_nii))
            data = img.get_fdata()
            # If 4D, select first N volumes; if 3D, just copy
            if data.ndim == 4:
                mag_data = data[..., :len(magnitude_indices)]
            else:
                mag_data = data
            mag_img = nib.Nifti1Image(mag_data, img.affine, img.header)
            nib.save(mag_img, str(bids_magnitude))
            print(f"Created magnitude fieldmap: {bids_magnitude.name}")
            # Optionally remove the intermediate file
            # full_nii.unlink()
            # Create JSON for magnitude
            magnitude_json = {
                "ConversionSoftware": "convert_parrec_to_nifti_bids.py",
                "ConversionSoftwareVersion": "2.0",
                "ConversionDate": datetime.now().isoformat(),
                "SourceFormat": "Philips PAR/REC",
                "SourceFiles": [
                    str(par_file),
                    str(par_file.with_suffix('.REC')),
                    str(par_file.with_suffix('.XML')),
                    str(par_file.with_suffix('.V41'))
                ],
                "BIDSModality": "fmap",
                "SubjectID": subject_id,
                "Units": "Hz",
                "IntendedFor": []  # Will be populated later
            }
            par_metadata = extract_par_metadata(par_file)
            magnitude_json.update(par_metadata)
            xml_file = par_file.with_suffix('.XML')
            xml_metadata = parse_xml_file(xml_file) if xml_file.exists() else {}
            magnitude_json["XMLMetadata"] = xml_metadata
            with open(bids_magnitude.with_suffix('.json'), 'w') as f:
                json.dump(magnitude_json, f, indent=2)
            return bids_magnitude
    except subprocess.CalledProcessError as e:
        print(f"Error extracting magnitude image: {e}\nstderr: {e.stderr}")
    return None

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