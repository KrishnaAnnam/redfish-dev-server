# BMC Redfish Simulator - Web UI

Comprehensive web interfaces for managing the BMC Redfish Simulator server and interacting with Redfish servers as a client.

## 📋 Overview

The Web UI package provides two separate interfaces:

1. **Server Web UI** - Configure, monitor, and control the Redfish simulator server
2. **Client Web UI** - Interact with and analyze Redfish servers

## 🚀 Quick Start

### Install Dependencies

```bash
# From the webui directory
pip install -r requirements_webui.txt

# Or from the project root
pip install -r webui/requirements_webui.txt
```

### Launch Server Web UI

```bash
# From the webui/server directory
python server_webui.py

# Or from project root
python webui/server/server_webui.py

# Custom host/port
python webui/server/server_webui.py -H 0.0.0.0 -p 5000
```

Access at: **http://127.0.0.1:5000**

### Launch Client Web UI

```bash
# From the webui/client directory
python client_webui.py

# Or from project root
python webui/client/client_webui.py

# Custom host/port
python webui/client/client_webui.py -H 0.0.0.0 -p 5001
```

Access at: **http://127.0.0.1:5001**

---

## 🖥️ Server Web UI

### Features

#### 🎛️ Server Control Panel
- **Start/Stop/Restart** - Full control over the simulator server
- **Real-time Status** - Monitor running state, PID, and uptime
- **Configuration** - Set host, port, mockup directory, platform type
- **SSL Support** - Enable/disable SSL/TLS

#### 📊 Live Monitoring
- **Request Statistics** - Total, successful, and failed requests
- **Real-time Logs** - View server logs with filtering (info/success/warning/error)
- **Performance Metrics** - Response times and server resource usage
- **Auto-refresh** - Status and logs update automatically every 2 seconds

#### ⚙️ Configuration Management
- **Mockup Selection** - Choose from available mockup directories
- **Platform Selection** - Select platform type (Generic, RAS-Enabled, Custom)
- **Port Configuration** - Customize server binding
- **SSL/TLS Options** - Enable secure connections

### Server UI Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/api/status` | GET | Get server status |
| `/api/start` | POST | Start the server |
| `/api/stop` | POST | Stop the server |
| `/api/restart` | POST | Restart the server |
| `/api/config` | GET/POST | Get or update configuration |
| `/api/logs` | GET | Get server logs |
| `/api/logs/clear` | POST | Clear logs |
| `/api/mockups` | GET | List available mockup directories |
| `/api/platforms` | GET | List available platform types |
| `/api/stats` | GET | Get server statistics |
| `/api/system` | GET | Get system information |

### Usage Example

1. **Open the Server Web UI** in your browser
2. **Configure the server**:
   - Host: `0.0.0.0`
   - Port: `8000`
   - Mockup: Select `public-rackmount1`
   - Platform: `generic`
3. **Click "Start Server"**
4. **Monitor the logs** and statistics in real-time
5. **Stop or restart** as needed

---

## 🔌 Client Web UI

### Features

#### 🔗 Connection Management
- **Multiple Connections** - Manage connections to multiple Redfish servers
- **Authentication Support** - Username/password authentication
- **SSL Verification** - Optional SSL certificate verification
- **Quick Switching** - Easily switch between connections

#### 🎯 Redfish Operations
- **GET Requests** - Retrieve resources
- **POST Requests** - Create resources and execute actions
- **PATCH Requests** - Update resources
- **DELETE Requests** - Remove resources
- **Custom Payloads** - JSON payload editor for POST/PATCH

#### 🔍 Discovery & Analysis
- **Resource Discovery** - Automatically discover all server resources
- **Server Analysis** - Analyze capabilities, features, and available services
- **Resource Counts** - View counts of Systems, Chassis, Managers
- **Service Detection** - Identify available Redfish services

#### 📊 Response Viewer
- **Formatted JSON** - Pretty-printed JSON responses
- **Response Metrics** - View response time and status
- **Syntax Highlighting** - Easy-to-read JSON display

#### 📜 Request History
- **Operation Log** - Track all requests and responses
- **Timestamps** - See when operations were performed
- **Error Tracking** - Identify failed requests
- **Performance Data** - Response time for each request

### Client UI Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/api/connections` | GET | List all connections |
| `/api/connections` | POST | Create new connection |
| `/api/connections` | DELETE | Close connection |
| `/api/get` | POST | Perform GET request |
| `/api/post` | POST | Perform POST request |
| `/api/patch` | POST | Perform PATCH request |
| `/api/delete` | POST | Perform DELETE request |
| `/api/discover` | POST | Discover all resources |
| `/api/analyze` | POST | Analyze server capabilities |
| `/api/history` | GET | Get request history |
| `/api/history/clear` | POST | Clear history |

### Usage Example

1. **Open the Client Web UI** in your browser
2. **Create a new connection**:
   - Name: `Local BMC Simulator`
   - URL: `http://localhost:8000`
   - (Optional) Username/Password
3. **Click "Connect"**
4. **Try operations**:
   - **Discover Resources** - Click to auto-discover all resources
   - **Analyze Server** - View server capabilities
   - **Manual Requests**:
     - Select method (GET/POST/PATCH/DELETE)
     - Enter path: `/redfish/v1/Systems`
     - Click "Execute Request"
5. **View results** in the Response tab
6. **Check history** in the History tab

---

## 🏗️ Architecture

### Server Web UI Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Frontend)                    │
│  - Dashboard with real-time updates                     │
│  - Configuration forms                                   │
│  - Log viewer with filtering                            │
│  - Statistics display                                    │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/REST API
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Flask Web Application                       │
│  - REST API endpoints                                    │
│  - ServerManager class                                   │
│  - Process management                                    │
│  - Log capture and filtering                            │
└─────────────────────────────────────────────────────────┘
                          │ subprocess
                          ▼
┌─────────────────────────────────────────────────────────┐
│           Redfish Simulator Server Process              │
│  - redfishMockupServer_enhanced.py                      │
│  - Serves Redfish API                                    │
│  - Platform-aware responses                             │
└─────────────────────────────────────────────────────────┘
```

### Client Web UI Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Frontend)                    │
│  - Connection manager                                    │
│  - Request builder (GET/POST/PATCH/DELETE)              │
│  - Response viewer                                       │
│  - Analysis dashboard                                    │
│  - History viewer                                        │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/REST API
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Flask Web Application                       │
│  - REST API endpoints                                    │
│  - ClientManager class                                   │
│  - Connection pooling                                    │
│  - Request history tracking                             │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/Redfish
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Redfish Client Library                      │
│  - RedfishClient class                                   │
│  - Authentication                                        │
│  - Request/response handling                            │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/HTTPS
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Target Redfish Server                       │
│  - Local simulator or remote BMC                        │
└─────────────────────────────────────────────────────────┘
```

---

## 🎨 User Interface Components

### Server Web UI Components

1. **Status Card**
   - Server state indicator (running/stopped)
   - PID display
   - Uptime counter
   - Start time
   - Control buttons (Start/Stop/Restart)

2. **Statistics Card**
   - Total requests counter
   - Successful requests
   - Failed requests
   - Real-time updates

3. **Configuration Card**
   - Host input
   - Port number
   - Mockup directory selector
   - Platform type selector
   - SSL/TLS checkbox

4. **Log Viewer**
   - Color-coded logs (info/success/warning/error)
   - Filter by level
   - Auto-scroll
   - Clear button
   - Refresh button

### Client Web UI Components

1. **Connection Sidebar**
   - List of active connections
   - Connection status indicators
   - Quick switch between connections
   - New connection button

2. **Quick Actions**
   - Discover Resources button
   - Analyze Server button
   - Clear History button

3. **Operations Panel**
   - Tabbed interface (Request/Response/Analysis/History)
   - Method selector (GET/POST/PATCH/DELETE)
   - Path input
   - Payload editor (for POST/PATCH)
   - Execute button

4. **Response Viewer**
   - Syntax-highlighted JSON
   - Response time badge
   - Status badge
   - Copy button

5. **Analysis Dashboard**
   - Resource count cards
   - Server information
   - Available services list
   - Protocol features

6. **History Panel**
   - Chronological request log
   - Success/error indicators
   - Timestamps
   - Response times

---

## 🔧 Advanced Configuration

### Environment Variables

```bash
# Server Web UI
export SERVER_WEBUI_HOST=0.0.0.0
export SERVER_WEBUI_PORT=5000
export SERVER_WEBUI_DEBUG=false

# Client Web UI
export CLIENT_WEBUI_HOST=0.0.0.0
export CLIENT_WEBUI_PORT=5001
export CLIENT_WEBUI_DEBUG=false
```

### Command Line Arguments

#### Server Web UI

```bash
python server_webui.py --help

Options:
  -H, --host HOST    Host to bind to (default: 127.0.0.1)
  -p, --port PORT    Port to bind to (default: 5000)
  --debug            Enable debug mode
```

#### Client Web UI

```bash
python client_webui.py --help

Options:
  -H, --host HOST    Host to bind to (default: 127.0.0.1)
  -p, --port PORT    Port to bind to (default: 5001)
  --debug            Enable debug mode
```

### Proxy Configuration

To run behind a reverse proxy (nginx, Apache):

```nginx
# Nginx example for Server Web UI
location /server-ui/ {
    proxy_pass http://127.0.0.1:5000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

# Nginx example for Client Web UI
location /client-ui/ {
    proxy_pass http://127.0.0.1:5001/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 📱 Browser Compatibility

| Browser | Version | Status |
|---------|---------|--------|
| Chrome | 90+ | ✅ Fully Supported |
| Firefox | 88+ | ✅ Fully Supported |
| Safari | 14+ | ✅ Fully Supported |
| Edge | 90+ | ✅ Fully Supported |

---

## 🔒 Security Considerations

### Authentication
- Web UIs do not currently implement authentication
- **Recommendation**: Use firewall rules or reverse proxy authentication
- Bind to `127.0.0.1` for local-only access

### SSL/TLS
- Web UIs run on HTTP by default
- **Recommendation**: Use reverse proxy with SSL for production
- Client UI supports connecting to HTTPS Redfish servers

### CORS
- CORS is enabled for development convenience
- **Recommendation**: Restrict CORS origins in production

---

## 🐛 Troubleshooting

### Server Web UI Issues

**Problem**: Server won't start
- Check if port 8000 is already in use
- Verify mockup directory exists
- Check file permissions

**Problem**: Logs not updating
- Verify auto-refresh is working (should refresh every 2 seconds)
- Check browser console for errors
- Try manual refresh button

**Problem**: Can't stop server
- Check if server process is running (ps aux | grep redfishMockupServer)
- Try restart button
- Kill process manually if needed

### Client Web UI Issues

**Problem**: Can't connect to server
- Verify server URL is correct
- Check if server is running
- Disable SSL verification if using self-signed certificates

**Problem**: Requests fail
- Check connection is established
- Verify path syntax starts with `/redfish/v1`
- Check server is responding (try in browser)

**Problem**: Blank responses
- Check browser console for errors
- Verify JSON syntax in payload (for POST/PATCH)
- Try a simple GET request first

---

## 📊 Performance

### Resource Usage

**Server Web UI**:
- Memory: ~50-100 MB
- CPU: <1% idle, 5-10% during operations

**Client Web UI**:
- Memory: ~50-100 MB
- CPU: <1% idle, 5-15% during operations

### Scalability
- Server Web UI: Supports managing one server instance
- Client Web UI: Supports multiple simultaneous connections
- Request History: Limited to last 100 entries (configurable)
- Log Storage: Limited to last 1000 entries (configurable)

---

## 🎯 Use Cases

### Development & Testing
1. **Start server** with Server Web UI
2. **Configure** platform and mockup
3. **Monitor logs** for debugging
4. **Test with Client UI** to verify responses

### Learning Redfish
1. **Use Client UI** to explore Redfish API
2. **Discover resources** automatically
3. **Analyze server** capabilities
4. **Experiment** with different operations

### Demonstration
1. **Side-by-side** Server and Client UIs
2. **Show real-time** log updates
3. **Demonstrate** platform-specific features
4. **Visualize** Redfish resource hierarchy

### Automated Testing
1. **Client UI** for manual test case execution
2. **History** for test result tracking
3. **Analysis** for feature verification

---

## 🚀 Future Enhancements

Planned features:

### Server Web UI
- [ ] Configuration profiles (save/load)
- [ ] Event subscription viewer
- [ ] Task monitor
- [ ] Multiple server instances
- [ ] Authentication support
- [ ] Webhook configuration

### Client Web UI
- [ ] Request templates library
- [ ] Response comparison tool
- [ ] Export history to CSV/JSON
- [ ] Batch operations
- [ ] Resource tree visualization
- [ ] Schema validation
- [ ] Mock response generator

---

## 📚 Additional Resources

- [Main README](../README.md)
- [Developer's Guide](../DEVELOPERS_GUIDE.md)
- [Platform Architecture](../PLATFORM_ARCHITECTURE.md)
- [Redfish API Documentation](https://www.dmtf.org/standards/redfish)

---

## 🤝 Contributing

Contributions to the Web UI are welcome!

Areas for contribution:
- UI/UX improvements
- Additional features
- Browser compatibility fixes
- Documentation enhancements
- Performance optimizations

---

## 📄 License

Same as the main BMC Redfish Simulator project (BSD 3-Clause License).

---

## 💬 Support

For issues or questions:
1. Check this documentation
2. Review the troubleshooting section
3. Check browser console for errors
4. Open an issue on GitHub

---

**Enjoy using the BMC Redfish Simulator Web UIs!** 🎉
