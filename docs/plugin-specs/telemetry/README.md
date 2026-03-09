# Telemetry Plugin Specification

**Telemetry Service Plugin for BMC Simulator**

## Overview

The Telemetry Plugin extends the BMC Simulator with capabilities for:
- Metric report collection and management
- Metric report definitions
- Metric definitions
- Telemetry data submission and streaming
- Trigger-based metric collection
- Subscriber notification for metric reports

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Telemetry Plugin                                │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Metric Reports │  │ Report Defs    │  │  Endpoints             │ │
│  │ - Collection   │  │ - Schedules    │  │  - /TelemetryService   │ │
│  │ - Caching      │  │ - Wildcards    │  │  - /MetricReports      │ │
│  │ - Streaming    │  │ - Aggregation  │  │  - /MetricDefinitions  │ │
│  └────────────────┘  └────────────────┘  └────────────────────────┘ │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐                             │
│  │ Triggers       │  │ Subscriber     │                             │
│  │ - Thresholds   │  │ Notification   │                             │
│  └────────────────┘  └────────────────┘                             │
│                                                                      │
└──────────────────────────────────────┬──────────────────────────────┘
                                       │
                            Uses Core Services
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BMC Simulator Core                                │
│   EventService │ LogService │ Platform Framework │ Handler Registry │
└─────────────────────────────────────────────────────────────────────┘
```

## Endpoints

### TelemetryService Root
- `GET /redfish/v1/TelemetryService` - Service root with capabilities

### Metric Reports
- `GET /redfish/v1/TelemetryService/MetricReports` - Collection of metric reports
- `GET /redfish/v1/TelemetryService/MetricReports/{id}` - Specific metric report

### Metric Report Definitions
- `GET /redfish/v1/TelemetryService/MetricReportDefinitions` - Collection
- `GET /redfish/v1/TelemetryService/MetricReportDefinitions/{id}` - Specific definition

### Metric Definitions
- `GET /redfish/v1/TelemetryService/MetricDefinitions` - Available metrics
- `GET /redfish/v1/TelemetryService/MetricDefinitions/{id}` - Specific metric

### Triggers
- `GET /redfish/v1/TelemetryService/Triggers` - Trigger collection
- `GET /redfish/v1/TelemetryService/Triggers/{id}` - Specific trigger

### Actions
- `POST /redfish/v1/TelemetryService/Actions/TelemetryService.SubmitTestMetricReport`

## Telemetry Data Submission

The plugin accepts telemetry data with the following parameters:

```json
{
  "MetricReportName": "CPUMetrics",
  "MetricReportValues": [
    {
      "MetricId": "CPUTemp",
      "MetricValue": "45",
      "Timestamp": "2026-01-22T10:30:00Z",
      "MetricProperty": "/redfish/v1/Systems/1/Processors/1#Temperature",
      "MetricDefinition": {
        "@odata.id": "/redfish/v1/TelemetryService/MetricDefinitions/CPUTemp"
      }
    }
  ]
}
```

## Subscriber Notification

When telemetry data is submitted, the plugin:
1. Validates the metric data
2. Builds a metric report
3. Caches the report
4. Updates the MetricReports collection
5. Notifies all valid subscribers asynchronously

## Platform Configuration

```yaml
platform:
  name: "Telemetry-Enabled Server"
  extensions:
    - telemetry
  
  telemetry:
    max_reports: 100
    retention_days: 7
    streaming_enabled: true
```

## Integration with EventService

The Telemetry plugin uses EventService subscriptions to notify clients:
- Subscriptions with appropriate EventTypes receive metric reports
- Reports are sent asynchronously to subscriber destinations
- HTTP headers include `Content-Type: application/json`

## Code Location

```
src/plugins/telemetry/
├── __init__.py           # Plugin exports
├── plugin.py             # Plugin registration and lifecycle
└── telemetry_service.py  # Telemetry service implementation
```
