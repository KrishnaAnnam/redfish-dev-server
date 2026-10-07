# MERC 3.1.1 - Micron Error Report Classifier

MERC is a machine learning engine for memory error classification and recommendations. It analyzes Intel retry read registers to classify memory failures and provide actionable recommendations for system administrators.

## Overview

MERC uses advanced ML techniques to improve recommendation accuracy and efficiency. The system processes Intel Xeon Scalable processor retry read data to classify memory errors and suggest appropriate remediation actions.

## Input Requirements

MERC accepts two input formats. Provide one (or both, in which case rows from each are concatenated):

- **Retry-read input** (`-i`): raw Intel retry-read registers; MERC decodes them internally.
- **Decoded input** (`-d`): pre-decoded DRAM addresses; use this when retry-read registers are not available but decoded fail addresses are.

### Retry-Read Input Format (`-i`)

Required columns:

- `msn` - Module Serial Number
- `mpn` - Micron Part Number
- `rr_log` - Intel retry read log register
- `rr_addr1` - Intel retry read address register 1
- `rr_addr2` - Intel retry read address register 2
- `rr_parity` - Intel retry read parity register
- `intel_hw_gen` - Intel Xeon Scalable hardware generation [1, 2, 3, 4]

#### Example

```csv
msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen
F1FB4E10,MTA18ASF2G72PZ-2G9E1,111113,75907332,36388,524288,2
2335C219,MTA36ASF4G72PZ-2G6E1,42509,83787793,39829,1066057944,1
D1CA57F7,MTC40F2046S1RC48BA1,4309513,63971328,140287,2290092032,3
```

#### Data types
msn, mpn: string

rr_log, rr_addr1, rr_addr2, rr_parity, intel_hw_gen: decimal int (hex values are not supported)

### Decoded Input Format (`-d`)

Use this format when you already have decoded DRAM addresses and do not have the raw retry-read registers. Required columns:

- `msn` - Module Serial Number
- `mpn` - Micron Part Number
- `bank` - DRAM bank address
- `row` - DRAM row address
- `col` - DRAM column address
- `dq` - DQ pin index within the device
- `device` - Device index on the module (integer index, or designator like `U25` / `DAR0B0` — non-numeric values are factorized internally)
- `module_rank` - Module rank index (e.g., 0 or 1)

#### Example (DDR4)

```csv
msn,mpn,bank,row,col,dq,device,module_rank
2EFCB8ED,MTA18ASF4G72PZ-3G2E1,9,249883,520,0,4,0
2D303BAE,MTA18ASF4G72PZ-3G2E1,6,222328,96,0,10,0
2FE847CD,MTA18ASF4G72PZ-3G2E1,7,235734,952,0,16,0
```

#### Example (DDR5)

```csv
msn,mpn,bank,row,col,dq,device,module_rank
4F968B0D,MTC20F2085S1RC48BA1,4,36889,976,0,0,0
4F9B0994,MTC20F2085S1RC48BA1,4,63923,928,0,0,1
D11ED4DA,MTC10F1084S1RC48BA1,23,367,256,0,7,0
```

#### Data types
msn, mpn: string

bank, row, col, dq, module_rank: decimal int (hex values are not supported)

device: decimal int or string designator

## Usage

```bash
./merc3 (-i INPUT_FILE | -d DECODED_FILE) -o OUTPUT_FILE [OPTIONS]
```

At least one of `-i` or `-d` must be provided. Both may be provided together.

### Required Arguments

- `-o, --output_csv OUTPUT_FILE` - Path where MERC output CSV will be saved

### Input Arguments (provide at least one)

- `-i, --input_csv INPUT_FILE` - Path to input CSV file containing retry-read register data
- `-d, --decoded_csv DECODED_FILE` - Path to input CSV file containing pre-decoded fail addresses

### Optional Arguments

- `-n, --num_cores N` - Number of CPU cores to use for processing (default: half of available cores)
  - If N >= 1: Use N cores
  - If N < 1: Use N as percentage of available cores (e.g., 0.5 = 50% of cores)

## Output

MERC generates a CSV file containing:

- Original input columns (`msn`, `mpn`)
- `predicted_class` - Classification of the memory error type
- `recommended_action` - Suggested remediation action
- `offline_range_1_max` - Upper bound of offline range 1 for supported design IDs
- `offline_range_1_min` - Lower bound of offline range 1 for supported design IDs
- offline ranges repeat for ranges 2, 3, and 4

### Example Output

```csv
msn,mpn,predicted_class,bank,offline_range_1_max,offline_range_1_min,offline_range_2_max,offline_range_2_min,offline_range_3_max,offline_range_3_min,offline_range_4_max,offline_range_4_min,recommended_action
F356DC1E,18ASF4G72PZ-2G9E1,block_of_rows,12,63487,62464,129023,128000,194559,193536,260095,259072,Offline specified memory ranges; schedule for removal when possible.
1FCEB16E,MTA36ASF4G72PZ-2G6E1,correctable,,,,,,,,,,Always correctable. Leave in place.
21CDDB57,MTA36ASF4G72PZ-2G6E1,high_severity,,,,,,,,,,High risk of UE. Schedule for removal ASAP.
1F6D87BA,MTA36ASF4G72PZ-2G6E1,dram_transient,,,,,,,,,,Transient DRAM error. Power cycle system, leave module in place. Not indicative of defectivity.
1FCDE79E,MTA36ASF4G72PZ-2G6E1,low_severity,,,,,,,,,,Very low risk. Leave in place.
1FCF5234,MTA36ASF4G72PZ-2G6E1,ppr_eligible,,,,,,,,,,Very low risk. May perform PPR if CE counts are too high.
1F70EE94,MTA36ASF4G72PZ-2G6E1,system_general,,,,,,,,,,Non-DRAM failure - may repeat. Investigate system for issues (socketing/training/etc.)
20ABFA33,MTC40F2046S1RC48BA1,system_socketing,,,,,,,,,,Poor socketing detected with high confidence. Not DRAM related. Re-seat module.
1FCDD0F1,MTC40F2046S1RC48BA1,system_transient,,,,,,,,,,Non-DRAM failure. Not expected to repeat. No action required.
```

## Error Classification Types

MERC classifies memory errors into the following categories and associated action recommendations:

- **`block_of_rows`**
  - *Recommended Action*: `Offline specified memory ranges; schedule for removal when possible.`

- **`correctable`**
  - *Recommended Action*: `Always correctable. Leave in place.`

- **`high_severity`**
  - *Recommended Action*: `High risk of UE. Schedule for removal ASAP.`

- **`dram_transient`**
  - *Recommended Action*: `Transient DRAM error. Power cycle system and leave module in place. Not indicative of defectivity.`

- **`low_severity`**
  - *Recommended Action*: `Very low risk. Leave in place.`

- **`ppr_eligible`**
  - *Recommended Action*: `Very low risk. May perform PPR if CE counts are too high.`

- **`system_general`**
  - *Recommended Action*: `Non-DRAM failure - may repeat. Investigate system for issues (socketing/training/etc.)`

- **`system_socketing`**
  - *Recommended Action*: `Poor socketing detected with high confidence. Not DRAM related. Re-seat module.`

- **`system_transient`**
  - *Recommended Action*: `Non-DRAM failure. Not expected to repeat. No action required.`

## Examples

### Retry-read input
```bash
./merc3 -i memory_errors.csv -o results.csv
```

### Decoded input
```bash
./merc3 -d decoded_addresses.csv -o results.csv
```

### Mixed input (both formats combined into a single run)
```bash
./merc3 -i memory_errors.csv -d decoded_addresses.csv -o results.csv
```

### Using Specific Number of Cores
```bash
./merc3 -i memory_errors.csv -o results.csv -n 4
```

### Using Percentage of Available Cores
```bash
./merc3 -i memory_errors.csv -o results.csv -n 0.75
```

## System Requirements

- Compatible with Intel Xeon Scalable processors (generations 1, 2, 3, and 4)
- Sufficient system memory for processing large datasets
- Multi-core processor recommended for optimal performance

## Supported Micron Design IDs

Z11B
Z21C
Z32D
Z41C
Z42B
Y32A
Y32B
Y52k

## Support

For technical support or questions about MERC, please contact your Micron representative.
