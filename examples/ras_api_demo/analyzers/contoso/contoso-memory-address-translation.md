# Contoso Demo Memory Address Translation

The `contoso-simple-v1` scheme is a deliberately simple, reversible mapping
between OS byte physical addresses and DDR5 x4 hierarchy coordinates. It is a
demo convention, not a generic DDR5 physical-address standard.

## Simplifying assumptions

- Every installed DIMM on the platform has the same capacity.
- Supported DIMM capacities are 32, 64, and 128 GiB.
- Every DIMM has two subchannels, eight bank groups per rank, four banks per
  bank group, and 2,048 columns per row.
- A raw DDR5 column selects four bytes. Sixteen columns form one 64-byte
  cacheline across the rank's DRAM devices.
- There is no XOR hashing, mirroring, remapping, or spare-row translation.
- The current topology has two sockets, two chiplets per socket, one memory
  controller per chiplet, two channels per controller, and two DIMMs per
  channel.

## Supported DIMM organizations

| DIMM size | Common organization | Ranks | Rows/bank | Columns/row |
| ---: | --- | ---: | ---: | ---: |
| 32 GiB | 1Rx4, 16 Gb x4 | 1 | 65,536 | 2,048 |
| 64 GiB | 2Rx4, 16 Gb x4 | 2 | 65,536 | 2,048 |
| 128 GiB | 2Rx4, 32 Gb x4 | 2 | 131,072 | 2,048 |

The capacity calculation is:

```text
4 bytes/column × 2,048 columns × rows/bank
× 4 banks/BG × 8 BG/rank × ranks × 2 subchannels
```

This yields exactly 32, 64, or 128 GiB.

## Address order

The encoder flattens fields in this high-to-low order:

```text
socket → chiplet → memory controller → channel → DIMM → subchannel
→ rank → bank group → bank → row → column → byte in column
```

The lowest two address bits select one byte of the four-byte column transfer.
The next eleven bits are the raw DDR5 column. Thus:

- Advancing one column advances four bytes.
- Advancing 16 columns advances one 64-byte cacheline.
- Advancing one row advances 8 KiB.
- A 4 KiB page cannot cross a row or DIMM boundary.

The DIMM size changes only the rank and row radices:

| DIMM | Rank values | Row values |
| ---: | ---: | ---: |
| 32 GiB | `0` | `0..65535` |
| 64 GiB | `0..1` | `0..65535` |
| 128 GiB | `0..1` | `0..131071` |

## Python API

```python
from memory_address_translation import (
    MemoryAddressConfiguration,
    MemoryChannelAddress,
    MemoryOrganization,
    memory_address_to_physical_address,
    physical_address_to_memory_address,
)

configuration = MemoryAddressConfiguration(MemoryOrganization(
    version=1,
    address_translation="contoso-simple-v1",
    dimm_size_gib=64,
))

location = MemoryChannelAddress(
    socket=0,
    chiplet=0,
    memory_controller=0,
    channel=0,
    dimm=1,
    subchannel=0,
    rank=0,
    bank_group=2,
    bank=3,
    row=1234,
    column=567,
)

physical_address = memory_address_to_physical_address(
    location, configuration)
assert physical_address_to_memory_address(
    physical_address, configuration) == location
```

## Injector CLI

```bash
python injector-contoso.py address-encode \
  --dimm-size-gib 64 \
  --socket 0 --chiplet 0 --memory-controller 0 \
  --channel 0 --dimm 1 --subchannel 0 --rank 0 \
  --bank-group 2 --bank 3 --row 1234 --column 567
```

```bash
python injector-contoso.py address-decode \
  --dimm-size-gib 64 \
  --physical-address 0x00000011609A48DC
```

Both commands emit JSON. `--endpoint-config` may replace `--dimm-size-gib`
and reads the platform's authoritative organization.

## Inventory-aware use

`ContosoMemoryAddressTranslator` combines the pure mapping with the endpoint's
installed-DIMM inventory. It rejects uninstalled addresses and resolves an OS
physical address to the DIMM's FRU ID and FRU text.

Page Offline uses this form. Every page in a CPAD section must resolve to the
descriptor FRU.
