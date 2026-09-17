# RAS Endpoint Configuration

The RAS endpoint simulator reads platform-owned endpoint settings from
`ras_endpoint_config.json` in the platform mockup directory:

```text
mockups/<platform>/ras_endpoint_config.json
```

The RAS Gen 1 platform uses
[`mockups/ras_gen1/ras_endpoint_config.json`](../../../mockups/ras_gen1/ras_endpoint_config.json).
Restart the server after changing this file.

The configuration is authoritative for:

- RAS endpoint identity and supported queues
- Internal memory-repair capabilities reported in Contoso CPERs
- Installed memory topology and DIMM capacities
- DIMM SPD identity data
- Per-DIMM repair limits

Memory-repair capabilities are not published on the Redfish RAS endpoint
resource. They are encoded in each Contoso memory-controller CPER.

## Top-Level Fields

| Field | Required | Description |
| --- | --- | --- |
| `platform_id` | Yes | Platform ID used by every configured endpoint. |
| `ras_endpoints` | Yes | Non-empty array of RAS endpoint definitions. |

Endpoint IDs and partition IDs must be unique within the file.

## Endpoint Fields

| Field | Required | Description |
| --- | --- | --- |
| `id` | Yes | Redfish RAS endpoint resource ID. |
| `creator_id` | Yes | Creator ID identifying the endpoint/analyzer owner. |
| `name` | Yes | Display name. |
| `partition_id` | Yes | Partition ID used to route CPERs and CPADs. |
| `description` | Yes | Endpoint description. |
| `endpoint_type` | Yes | Endpoint type, such as `Processor`. |
| `fru_id` | Yes | Field-replaceable unit ID. |
| `fru_text` | Yes | Human-readable FRU description. |
| `supported_queues` | Yes | CPER queues advertised by the endpoint. |
| `memory` | Yes | Installed-memory configuration for this endpoint. |

Identity and queue fields are published through Redfish discovery. Memory
repair capabilities are consumed internally and placed only in Contoso memory
CPERs.

## Memory Repair Capabilities

```json
{
  "soft_ppr_runtime_supported": true,
  "soft_ppr_boot_time_supported": true,
  "hard_ppr_boot_time_supported": true
}
```

| Field | Default | Meaning |
| --- | --- | --- |
| `soft_ppr_runtime_supported` | `false` | The endpoint can execute soft PPR immediately at runtime. |
| `soft_ppr_boot_time_supported` | `false` | Firmware supports soft PPR during boot. |
| `hard_ppr_boot_time_supported` | `false` | Firmware supports hard PPR during boot. |

All values must be JSON booleans. Runtime action `0x8001` is accepted for
execution only when `soft_ppr_runtime_supported` is `true`. Boot-time flags are
reported capabilities; boot-time repair queuing is not simulated yet.

The Contoso memory CPER stores these values in a one-byte bitfield:

| Bit | Capability |
| --- | --- |
| 0 | Soft PPR at runtime |
| 1 | Soft PPR at boot time |
| 2 | Hard PPR at boot time |
| 7:3 | Reserved; always zero |

## Memory Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| `memory_repair_capabilities` | No | All flags `false` | Internal PPR support flags reported in Contoso memory CPERs. |
| `channels_per_chiplet` | No | `2` | Channel slots on each chiplet. Valid range: 1-256. |
| `dimms_per_channel` | No | `2` | DIMM slots on each channel. Valid range: 1-256. |
| `memory_controllers` | Yes | None | Memory controllers and installed DIMMs. |

The Contoso demo has two chiplets (`0` and `1`) and one memory controller (`0`)
per chiplet. A DIMM entry means its slot is populated. Omit an entry to
simulate an empty slot.

Each memory controller contains:

| Field | Required | Description |
| --- | --- | --- |
| `chiplet` | Yes | Contoso chiplet index, `0` or `1`. |
| `controller` | Yes | Contoso memory-controller index; currently `0`. |
| `dimms` | Yes | Array of installed DIMMs; may be empty. |

## DIMM and SPD Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| `channel` | Yes | None | Channel containing the DIMM. |
| `dimm` | Yes | None | DIMM slot on the channel. |
| `size_bytes` | Yes | None | Positive DIMM capacity in bytes. |
| `max_repairs_per_bank` | No | `16` | Per-bank repair limit, from 0 through 255. |
| `spd` | Yes | None | SPD identity data captured in memory CPERs. |

`max_repairs_per_bank` value `0` disables repairs on that DIMM. A repair after
the configured limit fails without changing the bank count.

The `spd` object contains:

| Field | Required | CPER capacity | Description |
| --- | --- | --- | --- |
| `serial_number` | Yes | 18 ASCII characters | DIMM serial number. |
| `part_number` | Yes | 24 ASCII characters | DIMM part number. |
| `module_manufacturer_id` | Yes | 2 bytes | Module assembler JEP106 ID in DDR5 SPD order. |
| `dram_manufacturer_id` | Yes | 2 bytes | DRAM manufacturer JEP106 ID in DDR5 SPD order. |

The demo uses Microsoft for both manufacturer IDs:

```json
["0x04", "0xD5"]
```

## Minimal Example

This example configures one endpoint with one installed 64 GiB DIMM. Other
slots are empty. The complete RAS Gen 1 example contains two chiplets and eight
DIMMs in
[`ras_endpoint_config.json`](../../../mockups/ras_gen1/ras_endpoint_config.json).

```json
{
  "platform_id": "990f8820-bd4d-5064-58cc-961a053dea79",
  "ras_endpoints": [
    {
      "id": "Endpoint-1",
      "creator_id": "11111111-2222-3333-4444-555555555555",
      "name": "Contoso CPU Socket 0 RAS Endpoint",
      "partition_id": "22222222-3333-4444-5555-666666666666",
      "supported_queues": [
        "Fatal",
        "Recoverable",
        "Corrected",
        "Informational",
        "PlatformActionStatus"
      ],
      "description": "RAS API-capable endpoint for Contoso CPU socket 0",
      "endpoint_type": "Processor",
      "fru_id": "75824856-bd36-2cc8-61f4-39bb3276da2a",
      "fru_text": "Contoso CPU Socket 0",
      "memory": {
        "memory_repair_capabilities": {
          "soft_ppr_runtime_supported": true,
          "soft_ppr_boot_time_supported": true,
          "hard_ppr_boot_time_supported": true
        },
        "channels_per_chiplet": 2,
        "dimms_per_channel": 2,
        "memory_controllers": [
          {
            "chiplet": 0,
            "controller": 0,
            "dimms": [
              {
                "channel": 0,
                "dimm": 0,
                "size_bytes": 68719476736,
                "max_repairs_per_bank": 16,
                "spd": {
                  "serial_number": "MSFT-C0-CH0-D0",
                  "part_number": "MSFT-DDR5-64GB",
                  "module_manufacturer_id": ["0x04", "0xD5"],
                  "dram_manufacturer_id": ["0x04", "0xD5"]
                }
              }
            ]
          },
          {
            "chiplet": 1,
            "controller": 0,
            "dimms": []
          }
        ]
      }
    }
  ]
}
```

## Derived CPER Data

The endpoint computes `total_memory_bytes` by summing `size_bytes` for every
DIMM installed on that endpoint. Do not configure a separate total. The full
RAS Gen 1 configuration contains eight 64 GiB DIMMs, so its CPER value is
`549755813888` bytes (512 GiB).

When the endpoint emits a Contoso memory CPER, it overwrites submitted values
with authoritative configuration and runtime state for:

- SPD serial number and part number
- Module and DRAM manufacturer IDs
- Total endpoint memory
- Memory-repair capability bitfield
- Sparse per-DIMM bank repair counts

Repair counts reset to zero when the server restarts. Banks omitted from the
sparse repair list have zero repairs.

## Validation Rules

The plugin rejects invalid endpoint configuration, including:

- Duplicate endpoint IDs or partition IDs
- Missing endpoint identity fields
- Non-boolean repair capability values
- Chiplet, controller, channel, or DIMM indices outside configured limits
- Duplicate DIMM addresses
- Zero or negative DIMM capacities
- Repair limits outside `0..255`
- Missing, non-ASCII, or overlength SPD strings
- Invalid two-byte odd-parity JEP106 manufacturer IDs

Validate a file with the production loader:

```bash
.venv/bin/python -c 'from src.plugins.ras.memory_config import RASEndpointConfiguration; RASEndpointConfiguration.load("mockups/ras_gen1/ras_endpoint_config.json")'
```

## Start the Endpoint

```bash
python servers/redfishMockupServer_platform.py -D mockups/ras_gen1 -p 8000
```

The plugin finds `ras_endpoint_config.json` automatically. If it is absent,
controller-level errors remain available, but memory injections and PPR actions
fail because the endpoint has no authoritative memory configuration.