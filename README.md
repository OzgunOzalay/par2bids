# Philips PAR/REC to BIDS NIfTI Converter

This project converts Philips MRI scan files from PAR/REC format to BIDS-compliant NIfTI format with comprehensive JSON sidecar files.

## Overview

The converter processes Philips MRI scan files and outputs:
- **BIDS-compliant NIfTI files** (`.nii.gz`) with proper naming conventions
- **JSON sidecar files** (`.json`) containing comprehensive metadata from PAR and XML files
- **Ready-to-use dataset** for fMRIPrep and other BIDS-compatible tools

## Features

- ✅ Converts PAR/REC files to compressed NIfTI format
- ✅ Extracts metadata from PAR, XML, and V41 files
- ✅ Generates BIDS-compliant filenames and directory structure
- ✅ Creates comprehensive JSON sidecars with all relevant metadata
- ✅ Handles multiple scan types (anatomical, functional, field maps)
- ✅ Supports task-based naming for functional scans
- ✅ Preserves all original scan parameters and metadata

## File Structure

```
Nikki/
├── XMLPARREC/                          # Input directory
│   ├── *.PAR                           # Parameter files
│   ├── *.REC                           # Raw image data
│   ├── *.XML                           # Extended metadata
│   └── *.V41                           # Additional parameters
├── NIfTI_BIDS/                         # Output directory
│   ├── sub-*_ses-*_task-*_bold.nii.gz  # Functional scans
│   ├── sub-*_ses-*_task-*_bold.json    # Functional metadata
│   ├── sub-*_ses-*_T1w.nii.gz          # T1 anatomical scans
│   ├── sub-*_ses-*_T1w.json            # T1 metadata
│   ├── sub-*_ses-*_T2w.nii.gz          # T2 anatomical scans
│   ├── sub-*_ses-*_T2w.json            # T2 metadata
│   ├── sub-*_ses-*_phasediff.nii.gz    # Field maps
│   └── sub-*_ses-*_phasediff.json      # Field map metadata
├── convert_parrec_to_nifti_bids.py     # Main conversion script
├── requirements.txt                     # Python dependencies
└── README.md                           # This file
```

## BIDS Naming Convention

The converter generates BIDS-compliant filenames following this pattern:

```
sub-{subject}_ses-{session}_acq-{acquisition}_task-{task}_run-{run}_{suffix}.nii.gz
```

### Examples:
- `sub-Blackford_ses-04_acq-wipfunctresting_task-rest_bold.nii.gz`
- `sub-Blackford_ses-08_acq-wipanticipation1_task-anticipation_run-1_bold.nii.gz`
- `sub-Blackford_ses-02_acq-wipt1w3dtfesense_T1w.nii.gz`
- `sub-Blackford_ses-06_acq-wipaxb0map_phasediff.nii.gz`

## Installation

1. **Clone or download this repository**
2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install required system tools:**
   ```bash
   # For parrec2nii (recommended)
   conda install -c conda-forge parrec2nii
   
   # Alternative: dcm2niix
   sudo apt-get install dcm2niix
   ```

## Usage

### Basic Conversion

1. **Place your PAR/REC files in the `XMLPARREC/` directory**
2. **Run the conversion script:**
   ```bash
   python3 convert_parrec_to_nifti_bids.py
   ```

3. **Check the output in `NIfTI_BIDS/` directory**

### Input File Requirements

Your `XMLPARREC/` directory should contain:
- **PAR files**: Parameter files with scan metadata
- **REC files**: Raw image data files
- **XML files**: Extended metadata (optional but recommended)
- **V41 files**: Additional parameter files (optional)

### Output

The script will create:
- **Compressed NIfTI files** (`.nii.gz`) with BIDS-compliant names
- **JSON sidecar files** (`.json`) with comprehensive metadata
- **Log output** showing conversion progress and any errors

## Supported Scan Types

The converter automatically detects and categorizes scan types:

| Protocol Name | BIDS Suffix | Modality | Description |
|---------------|-------------|----------|-------------|
| T1W/T1 | T1w | anat | T1-weighted anatomical |
| T2W/T2 | T2w | anat | T2-weighted anatomical |
| Funct/Resting | bold | func | Resting state functional |
| Anticipation* | bold | func | Task-based functional |
| Test_epi | bold | func | EPI test scans |
| B0map | phasediff | fmap | Field maps |
| Survey | scout | anat | Scout/survey scans |

## JSON Sidecar Contents

Each JSON sidecar contains:

### BIDS Required Fields
- `ConversionSoftware`: Software used for conversion
- `ConversionDate`: Date and time of conversion
- `SourceFormat`: Original file format (Philips PAR/REC)

### Scan Parameters
- `RepetitionTime`: TR in milliseconds
- `EchoTime`: TE in milliseconds
- `FlipAngle`: Flip angle in degrees
- `SliceThickness`: Slice thickness in mm
- `FieldOfView`: Field of view dimensions
- `ScanResolution`: Scan resolution

### Geometric Information
- `Angulation`: Slice angulation
- `OffCentre`: Off-center position
- `PatientPosition`: Patient position

### Sequence Information
- `Technique`: MRI technique used
- `ScanMode`: Scan mode (2D/3D)
- `ProtocolName`: Original protocol name

### Additional Metadata
- All PAR file metadata
- All XML file metadata (if available)
- Source file references

## Troubleshooting

### Common Issues

1. **"Varying slice orientation" error**
   - Some survey/scout scans may have varying slice orientations
   - This is a limitation of the conversion tool
   - These scans will be skipped

2. **Missing XML files**
   - XML files are optional but provide additional metadata
   - Conversion will proceed without them

3. **Permission errors**
   - Ensure you have write permissions in the output directory
   - Make sure scripts are executable: `chmod +x *.py`

### File-specific Issues

- **Functional scans**: May have multiple volumes (4D data)
- **Large files**: May require significant memory and time
- **EPI scans**: May have different geometric parameters

## Integration with fMRIPrep

The converted files are ready for fMRIPrep:

```bash
# Example fMRIPrep command
fmriprep /path/to/NIfTI_BIDS /path/to/output participant --participant-label sub-Blackford
```

## Dependencies

### Python Packages
- `nibabel`: NIfTI file handling
- `numpy`: Numerical operations
- `xml.etree.ElementTree`: XML parsing (built-in)

### System Tools
- `parrec2nii`: PAR/REC to NIfTI conversion
- Alternative: `dcm2niix` for some file types

## Contributing

To contribute to this project:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is provided as-is for research and educational purposes.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the log output for specific error messages
3. Ensure all dependencies are properly installed
4. Verify input file format and structure

## Version History

- **v2.0**: BIDS-compliant conversion with comprehensive metadata
- **v1.0**: Basic PAR/REC to NIfTI conversion 