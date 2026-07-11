# Contoso CPER Sections

This document describes CPER sections for a fictional Contoso SoC that supports the RAS API.  It is intended to be an educational example of how to create CPERs for analysis.
The RAS API demo will inject these errors into the Contoso RAS API Endpoint.  The CPERs will be collected and analyzed in the demo.

## CPER Section Contents

The Contoso CPER sections contain Error Banks that identify which error occurred and other registers that are useful in understanding the error.

The Contoso SoC is composed of subcomponents like cores, memory controllers and PCIe root ports.  Each subcomponent logs different errors and have a distinct CPER section-type to contain their error logs.

## Contoso Error Bank Definition

These CPERs are intended to be representative of typical CPUs.  Most CPUs have a set of error logging registers such as Machine Check Banks or Error Records which have common traits.  The Contoso Error Bank adopts common characteristics of these sets of error registers, but simplified for this demo.

The Contoso Error Bank has these registers, all 64-bits:
* error status register
* error address
* error misc 0
* error misc 1

Implementation-specific fields in the Error Banks are specific to a specific subcomponent in a specific Contoso silicon product.  Examples of subcomponents include CPU cores, memory controllers and PCIe root ports.  

When Error banks are captured in CPERs, decoders use the CPER Section-Type to determine which subcomponent's errors were captured in the CPER. The section-type is defined to have specific sets of registers from a specific part of a specific generation of a chip, including specific Error Banks.  If an Error Bank is in a CPER section we know which subcomponent the Error Bank is associated with. This permits the decoder to know how to interpret error banks in the CPER.

### Error Status Register

The Error Status Register is cleared to all zeros.  When hardware logs an error, this register captures details about the error.

The register layout is (bit 0 is the least-significant bit):

| Bits | Width | Field | Description |
| --- | --- | --- | --- |
| 63 | 1 | Address Valid | Set when the Error Address register is valid |
| 62 | 1 | Overflow | Set if multiple errors are detected before the error is cleared |
| 61:59 | 3 | Severity | Error severity (see the Severity values below) |
| 58:16 | 43 | Reserved | Reserved |
| 15:0 | 16 | errorID | Implementation-specific identifier for the logged error |

The Severity field encodes:

| Value | Severity | CPER Severity |
| --- | --- | --- |
| 0 | No error logged |  N/A |
| 1 | Fatal | Fatal |
| 2 | Uncorrected | Fatal |
| 3 | Recoverable | Recoverable |
| 4 | Deferred | Informational |
| 5 | Corrected | Corrected |

The per-error "Severity" listed in each Error Bank's ErrorID table is the *typical* severity for that error. At runtime the Severity field in the Error Status Register is authoritative and may differ (for example, escalated on overflow).  The Contoso SoC, like most other SoCs, has a Contoso-specific definition of error severities.  The Error Status Register always logs the Contoso-specific severity.  The CPER severity is derived from the Contoso severity as shown in the table above.  This is typical of SoCs and the mapping reflects current industry best practices.

The errorID field is in the low-order bits and is an implementation-specific enumeration that identifies which error was logged. A value of zero means that no error has been logged.

### Error Address

The Error Address register contains the physical address of the error.  It is only valid when the Error Status Register's Address Valid Bit is set.

### Misc 0

The Misc 0 register contains additional data about the errors logged in the Error Bank.

The register layout is (bit 0 is the least-significant bit):

| Bits | Width | Field | Description |
| --- | --- | --- | --- |
| 63 | 1 | Injected | Set if the error was injected or spoofed (it is not a naturally occurring error) |
| 62:16 | 47 | Implementation specific | Implementation-specific context |
| 15:0 | 16 | ce_count | Count of corrected errors detected since the Error Bank was last cleared |

### Misc 1

The Misc 1 register contains additional, implementation specific context.

## Contoso Standard Section Layout

CPER sections are binary structures that can contain data in a vendor-specific format. There are standard formats for CPERs which are sometimes used by an OS to react to errors, but those CPERs are very limited in terms of the data that can be captured.  For the RAS API we want richer data that we can use to infer root causes and improve silicon quality. This binary format allows silicon vendors to include proprietary data.

The Contoso sections are designed to have just enough detail to illustrate essential analysis techniques.

All Contoso section structures, including the section header, error banks, and additional-register blocks, are little-endian and packed (no implicit padding between fields).


### Contoso Standard CPER Section Format

The CPER standard requires that section bodies be interpreted by looking at their section-type.  There is no standard for proprietary section types, but it is a good practice to implement vendor-specific standards to make CPER sections easier to decode.  This Contoso example implements a simple Contoso-specific CPER section standard to show how this might be done.

The Contoso Standard CPER section has a header for the section followed by one or more sets of error banks and registers associated with the error bank as shown in the example below.

<table border="1" cellpadding="6" cellspacing="0">
<tr><td>Header</td></tr>
<tr><td>First Error Bank</td></tr>
<tr><td>Second Error Bank</td></tr>
<tr><td>Additional Registers for First Error Bank</td></tr>
<tr><td>Additional Registers for Second Error Bank</td></tr>
</table>

#### Contoso Section Header
The Contoso CPER Section Header contains:

| Field | Size |
| --- | --- |
| Contoso CPER Section Format Major Version number | 1 byte |
| Contoso CPER Section Format Minor Version number | 1 byte |
| Number of pairs of Error Banks and Register sets in the section format | 2 bytes |
| Subcomponent Instance ID | 4 bytes |
| **Total** | **8 bytes** |

The subcomponent instance ID is specific to a subcomponent.  The CPER section type tells us what type of subcomponent is being logged in the section body and the subcomponent instance ID tells us which instance of that subcomponent is being logged.  For example, the section type might be for a CPU core and the subcomponent instance ID might be the core number.  Each CPER section type definition will define how these bits are defined.

#### Contoso Error Bank Format

The Contoso Error Banks are stored using the following format:

| Field | Size |
| --- | --- |
| Error Status Register | 8 bytes |
| Error Address | 8 bytes |
| Error Misc 0 | 8 bytes |
| Error Misc 1 | 8 bytes |
| Offset to Additional Registers for this Error Bank | 4 bytes |
| Reserved | 4 bytes |
| **Total** | **40 bytes** |

The offset to the additional registers is from the start of the error section.  If the offset is equal to zero, no additional registers are present.

The format of the additional registers is specific to the section type.

## Contoso CPER Section Type Definitions

The Contoso SoC is a simple chip for illustrating how to create rich, parsable CPER sections and only supports a few section types.  The definitions for the section types follow.  Note that, if there were multiple generations of Contoso SoCs, each generation of the Contoso SoC might log different errors and might have a different section type GUID.

### CPU Core - First Generation

**CPER Section Type GUID:** `f63f509b-8995-4efd-9144-4b7fed6c4fd3`

The Contoso CPU Core Section breaks the Subcomponent Instance ID into two 2-byte fields:

| Field | Size |
| --- | --- |
| Chiplet number | 2 bytes |
| Core number on the chiplet | 2 bytes |
| **Total** | **4 bytes** |

The Contoso SoC for the purpose of the demo has 1 chiplet containing all of the cores.

This is illustrative of how silicon component vendors can create a coordinate system within their SoCs.  They have the flexibility to define headers in their section types that enable them to reference subcomponents using a schema that is convenient for their designs.  Note that this format does not track the socket number because that is implied in the CPER Header's partitionID, but this is illustrative and silicon component vendors might want to include it in their section-body coordinates.  

The Contoso CPU Core - First Generation, has the following error banks and associated additional registers.

#### Error Bank 0: Core Errors

Error Bank 0 logs Core errors:

| ErrorID | Error Name | Severity |
| --- | --- | --- |
| 0x00 | No Error Logged | No error logged |
| 0x01 | Poison Consumption | Recoverable |
| 0x02 | Transaction Timeout | Fatal |
| 0x03 | Register Parity Error | Fatal |
| 0x04 | Cache Corrected ECC Error | Corrected |
| 0x05 | Cache Uncorrected ECC Error | Deferred |
| 0x06 | Hardware Assert | Fatal |

ErrorID 0x05 is detected as uncorrected but reported as *Deferred* because the poisoned data is not consumed at logging time.

Additional Registers for Bank 0 Errors:


```c
uint64_t timeout_transaction_details;   // 8
uint64_t register_parity_details;       // 8
uint64_t cache_location;                // 8
uint64_t assert_details;                // 8
uint64_t core_debug_details;            // 8

// Total: 40 bytes
```
These additional registers are included in this demo to illustrate that CPER error logs should be rich, with all the information that is available and might help debug a hardware problem.  Since this is for a demo, the details in the registers will not be provided. 


### Contoso Memory Controller - First Generation

**CPER Section Type GUID:** `e01ce992-d080-43f4-8a2c-df8a9d81eb4e`

The Contoso Memory Controller section breaks the Subcomponent Instance ID into two 2-byte fields:

| Field | Size |
| --- | --- |
| Chiplet number | 2 bytes |
| Controller Number on the chiplet | 2 bytes |
| **Total** | **4 bytes** |

The Contoso SoC for the purpose of this demo has 2 chiplets.

The Contoso Memory Controller has the following error banks and associated additional registers.


#### Error Bank 0: DRAM Errors

Error Bank 0 logs DRAM errors:

| ErrorID | Error Name | Severity |
| --- | --- | --- |
| 0x00 | No Error Logged | No error logged |
| 0x01 | Corrected Memory ECC Error | Corrected |
| 0x02 | Uncorrected Memory ECC Error | Deferred |
| 0x03 | Command/Address Parity Error | Uncorrected |

ErrorID 0x02 is detected as uncorrected but reported as *Deferred* because the poisoned data is not consumed at logging time.

Additional Registers for Bank 0 Errors:

Note that, for simplicity, the Contoso memory controller assumes DDR5 10x4 which has 10 DRAMs, 4 DQs with 16 beats of data.

```c
uint8_t  channel;          // 1
uint8_t  subchannel;       // 1
uint8_t  dimm;             // 1
uint8_t  rank;             // 1
uint8_t  bank_group;       // 1
uint8_t  bank;             // 1
uint32_t row;              // 4
uint16_t column;           // 2
uint16_t syndrome;         // 2
uint16_t beat_mask[10][4]; // 80  -- [DRAM][DQ]; each bit is one of 16 beats of a DQ
// Total: 94 bytes
```


#### Error Bank 1: Other Errors 

Error Bank 1 logs other errors in the memory controller:

| ErrorID | Error Name | Severity |
| --- | --- | --- |
| 0x00 | No Error Logged | No error logged |
| 0x01 | DLL Lock Error | Fatal |
| 0x02 | Internal Corrected Error | Corrected |
| 0x03 | Internal Uncorrected Error| Fatal |
| 0x04 | Mesh Error | Fatal |

```c
uint32_t DllLockLossInfo; // 4  -- more details about DLL Lock errors
uint16_t ErrorStructure;  // 2  -- structure in the memory controller that had the error
uint16_t OtherMeshEntity; // 2  -- ID of the other mesh entity involved in mesh errors
// Total: 8 bytes
```  

Future Generations of Contoso SoCs can append definitions of their CPER sections to this file.