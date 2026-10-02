# Change Log

## [Unreleased] - 2026-10-02
### Added - RAS Plugin SDK Integration
- RAS plugin loading through the shared Plugin SDK used by all server variants
- Gen1 platform configuration with structured RAS plugin settings
- Focused Plugin SDK adapter and imported RAS regression coverage
- Documentation links for the plugin, endpoint configuration, and demo assets

## [2.2.0] - 2026-01-23
### Major Changes - RAS Plugin Initial Implementation
- OCP RAS API plugin for discovery, CPAD handling, CPER LogService storage,
  endpoint configuration, and reset-aware deferred actions
- Gen1 mockup, analyzer/demo assets, and focused RAS regression tests

### Added
- `src/plugins/ras/` - RAS plugin implementation and documentation
- `mockups/ras_gen1/` - RAS-enabled mockup data
- `examples/ras_api_demo/` - Analyzer, policy, event-listener, and demo assets
- `tests/test_ras_plugin_sdk.py` - Shared Plugin SDK adapter coverage
- RAS-focused endpoint, CPAD, analyzer, encoder, policy, namespace, and memory
  tests under `tests/`

### Fixed
- Fixed POST handler body consumption bug in `redfishMockupServer_platform.py`
- Fixed module path issue for server startup
- Fixed event subscription response handling

### Cleanup
- Moved 6 development status files to `archive/` (PHASE_*.md, LIBCPER_*.md, RAS_COMPLETE_INTEGRATION.md)
- Removed duplicate CPAD sample files from `examples/ras/cpad_samples/`
- Removed obsolete `servers/redfishMockupServer_ras.py` (superseded by _platform.py)
- Removed orphan demo files (`demo_parser_config.py`, `demo_python_parser.py`, `ras_plugin_standalone_demo.py`)

### RAS Plugin Features
- CPAD (Corrective Platform Action Descriptor) submission and validation
- CPER (Common Platform Error Record) generation using libcper templates
- Configured endpoint identity, ownership, topology, and memory inventory
- LogService integration with Redfish-compliant log entries
- Reset notification for deferred endpoint actions
- External analyzer and policy demonstration workflow

## [2.1.0] - 2025-12-03
### Major Changes
- Separated vendor-specific simulator into independent repository
- Complete repository cleanup and reorganization
- Added comprehensive Related Projects section to README
- Updated contributor attribution to Hari Ramachandran

### Removed
- Removed vendor-specific simulator directory (34 files, moved to separate repo)
- Removed vendor-specific documentation (5 files)
- Archived working/meta documents (5 files)

### Added
- CLEANUP_SUMMARY.md documenting repository separation
- VIRTUAL_REDFISH_PLATFORM_GUIDE.md for mockup server documentation
- Enhanced training materials and demo examples
- GitHub topics for better discoverability

### Documentation
- Updated README with Related Projects section
- Refined focus on generic DMTF Redfish simulation
- Clear separation between generic and vendor-specific development

### Repository Focus
- Refined focus on generic DMTF Redfish simulation
- BSD 3-Clause license (vendor-neutral, educational)
- Stable, well-tested generic simulator

## [1.2.4] - 2023-12-01
- Added better handling of resource creation operations to not rely on a resource identifier to be given
- Added the  response header when a new session is created

## [1.2.3] - 2023-05-15
- Fixes to SSDP listener to bind to all interfaces as well as enable listening on the loopback address

## [1.2.2] - 2023-02-24
- Updated bundled mockup to match 2022.3 release of public-rackmount1

## [1.2.1] - 2023-01-20
- Added support for binary files in a mockup

## [1.2.0] - 2023-01-13
- Import Mapping from collections.abc to support Python 3.10

## [1.1.9] - 2022-08-12
- Added SIGTERM handler to close the server

## [1.1.8] - 2022-06-03
- Added baseline support for the '$expand' query parameter

## [1.1.7] - 2021-07-02
- Added Content-Length header to responses for statically built /redfish

## [1.1.6] - 2021-06-18
- Added Content-Length header to responses

## [1.1.5] - 2021-02-15
- Made changes to hide `HttpHeaders` contents in event subscriptions

## [1.1.4] - 2020-11-13
- Added built-in "public-rackmount1" mockup

## [1.1.2] - 2020-10-30
- Made enhancement to collection management to fill in `Id` and `@odata.id` properly

## [1.1.1] - 2020-10-19
- Added Dockerfile to run the server as a Docker container
- Added expand support for resource collections

## [1.1.0] - 2020-05-09
- Added ability to POST to actions shown in the mockups so that a 2xx code is returned

## [1.0.9] - 2020-03-21
- Made corrections to the spelling of SSDP in the code

## [1.0.8] - 2019-03-26
- Fixed some issues with command line argument handling
- Fixed SSDP functionality
- Fixed issues with pathing on Windows

## [1.0.7] - 2019-02-08
- Fixed handling of PATCH/POST/PUT requests that do not contain a JSON body
- Added support for the SubmitTestMetricReport action

## [1.0.6] - 2018-10-12
- Added SSDP support within the service
- Added support for $top and $skip

## [1.0.5] - 2018-09-07
- Added Transfer-Encoding to the list of HTTP headers to not use

## [1.0.4] - 2018-07-16
- Fixed behavior of how the URIs are managed when issuing DELETE to members of a collection
- Added Location header in the service response when creating new resources

## [1.0.3] - 2018-05-25
- Added logic to remove the @Redfish.Copyright statement from payloads

## [1.0.2] - 2018-05-11
- Corrected Submit Test Event Action; it now verifies all required parameters are given, and the format of the Event it sends matches the Event schema

## [1.0.1] - 2018-04-13
- Made fixes for how POST and DELETE are handled with the Event Destination Collection
- Made fixes to the Submit Test Event action

## [1.0.0] - 2018-02-02
- Added support for HTTPS
- Added support for using "short" mockups (ones without the /redfish/v1 resource)
- Added support for submitting test events
- Added support for PATCH and PUT

## [0.9.7] - 2017-03-10
- Added support to delay time from json for GET and HEAD API  
    - "-T" option to include delay in time. If option not specified, there is no delay in response. Checks for time.json.
    - "-t <time_in_seconds>" to specify default time if time.json is not present.
- Added Response Header support for GETs: 
    - Checks for headers.json and includes required headers from it.
    - Certain headers like ("Connection", "Keep-Alive", "Content-Length") are not included in GET request.
- Added Support for HEAD Method
    - Checks for headers.json and includes required headers from it.
- Changed TestETag option to "-E" from "-T" 

## [0.9.3] - 2016-12-05
- -t <responseTime> option to specify a response delay for responses--to simulate a real system better
- fixed bug where GET /redfish/v1/$metadata was not being returned

## [0.9.2] - 2016-09-07
- added flush to server prints so that buffered stdout on cygwin would work
- added -T option to enable returning fake etags on certain APIs -instead of always doing it
- added -D <dir>  option  where <dir> is the abs or relative path to the mockup.  if no -D option, then CWD is assumed

## [0.9.1] - 2016-09-06
- Initial Public Release
