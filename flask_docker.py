from flask import Flask, render_template, request, jsonify
import docker
import time
import os

app = Flask(__name__)
docker_client = None

def init_docker():
    global docker_client
    try:
        docker_client = docker.from_env()
        docker_client.ping()
        return True
    except:
        try:
            docker_client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            docker_client.ping()
            return True
        except:
            docker_client = None
            return False

class ContainerManager:
    def __init__(self):
        self.container = None
        self.container_id = None
        self.running = False

    def start(self, image_name="hello-world"):
        if not docker_client:
            return False, "Docker not available"
        
        if self.running:
            return False, "Container already running"

        try:
            docker_client.ping()
        except:
            return False, "Cannot connect to Docker"

        try:
            docker_client.images.get(image_name)
        except docker.errors.ImageNotFound:
            try:
                docker_client.images.pull(image_name)
            except Exception as e:
                return False, f"Failed to pull {image_name}: {str(e)}"

        try:
            ports = {}
            if image_name in ['nginx', 'httpd']:
                ports = {'80/tcp': 8080}

            self.container = docker_client.containers.run(
                image_name,
                detach=True,
                remove=False,
                name=f"app_container_{int(time.time())}",
                ports=ports if ports else None
            )
            
            self.container_id = self.container.id
            self.running = True
            
            return True, f"Started: {self.container_id[:12]}"
            
        except Exception as e:
            return False, f"Start failed: {str(e)}"

    def stop(self):
        if not self.running or not self.container:
            return False, "No container running"

        try:
            self.container.stop()
            self.container.remove()
            
            self.container = None
            self.container_id = None
            self.running = False
            
            return True, "Container stopped"
            
        except docker.errors.NotFound:
            self.container = None
            self.container_id = None
            self.running = False
            return True, "Container removed"
        except Exception as e:
            return False, f"Stop failed: {str(e)}"

    def status(self):
        if self.running and self.container:
            try:
                self.container.reload()
                return {
                    'running': True,
                    'container_id': self.container_id[:12],
                    'status': self.container.status
                }
            except:
                self.running = False
                self.container = None
                self.container_id = None
        return {'running': False}

manager = ContainerManager()

@app.route('/')
def index():
    return render_template('index.html', status=manager.status())

@app.route('/start', methods=['POST'])
def start_container():
    data = request.get_json() or {}
    image = data.get('image', 'hello-world')
    
    success, message = manager.start(image)
    
    return jsonify({
        'success': success,
        'message': message,
        'status': manager.status()
    })

@app.route('/stop', methods=['POST'])
def stop_container():
    success, message = manager.stop()
    
    return jsonify({
        'success': success,
        'message': message,
        'status': manager.status()
    })

@app.route('/docker-info')
def docker_info():
    if not docker_client:
        return jsonify({
            'connected': False,
            'error': 'Docker not initialized'
        })
    
    try:
        info = docker_client.info()
        version = docker_client.version()
        return jsonify({
            'connected': True,
            'docker_version': version.get('Version', 'Unknown'),
            'containers_running': info.get('ContainersRunning', 0),
            'containers_total': info.get('Containers', 0)
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'error': str(e)
        })

@app.route('/status')
def get_status():
    return jsonify(manager.status())

def create_html():
    os.makedirs('templates', exist_ok=True)
    
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>Docker Controller</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #333; }
        .input-group { text-align: center; margin: 20px 0; }
        .input-group input { padding: 10px; font-size: 16px; border: 1px solid #ddd; border-radius: 5px; width: 300px; }
        .input-group label { display: block; margin-bottom: 10px; font-weight: bold; }
        .buttons { display: flex; justify-content: center; gap: 20px; margin: 30px 0; }
        .btn { padding: 15px 30px; font-size: 18px; border: none; border-radius: 5px; cursor: pointer; min-width: 150px; }
        .btn:disabled { background: #6c757d; cursor: not-allowed; }
        .start-btn { background: #28a745; color: white; }
        .start-btn:hover:not(:disabled) { background: #218838; }
        .stop-btn { background: #dc3545; color: white; }
        .stop-btn:hover:not(:disabled) { background: #c82333; }
        .status { text-align: center; margin: 20px 0; padding: 15px; border-radius: 5px; font-weight: bold; }
        .status.running { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.stopped { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .message { text-align: center; margin: 10px 0; padding: 10px; border-radius: 5px; }
        .message.success { background: #d4edda; color: #155724; }
        .message.error { background: #f8d7da; color: #721c24; }
        #loading { display: none; text-align: center; margin: 20px 0; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>Docker Controller</h1>
        
        <div id="dockerStatus" class="status">
            <div class="status stopped">Checking Docker...</div>
        </div>
        
        <div class="input-group">
            <label for="imageInput">Docker Image:</label>
            <input type="text" id="imageInput" value="hello-world" placeholder="Image name">
            <p><small>Examples: hello-world, nginx, ubuntu, python:3.9</small></p>
        </div>
        
        <div class="buttons">
            <button id="startBtn" class="btn start-btn" onclick="startContainer()">Start</button>
            <button id="stopBtn" class="btn stop-btn" onclick="stopContainer()">Stop</button>
        </div>
        
        <div id="loading">
            <div class="spinner"></div>
            <p>Processing...</p>
        </div>
        
        <div id="status" class="status">
            {% if status.running %}
                <div class="status running">
                    Container Running<br>
                    ID: {{ status.container_id }}<br>
                    Status: {{ status.status }}
                </div>
            {% else %}
                <div class="status stopped">No Container Running</div>
            {% endif %}
        </div>
        
        <div id="message"></div>
    </div>

    <script>
        function showLoading() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = true;
        }
        
        function hideLoading() {
            document.getElementById('loading').style.display = 'none';
        }
        
        function updateStatus(status) {
            const statusDiv = document.getElementById('status');
            if (status.running) {
                statusDiv.innerHTML = `
                    <div class="status running">
                        Container Running<br>
                        ID: ${status.container_id}<br>
                        Status: ${status.status}
                    </div>`;
            } else {
                statusDiv.innerHTML = '<div class="status stopped">No Container Running</div>';
            }
            
            document.getElementById('startBtn').disabled = status.running;
            document.getElementById('stopBtn').disabled = !status.running;
        }
        
        function showMessage(message, isSuccess) {
            const messageDiv = document.getElementById('message');
            messageDiv.innerHTML = `<div class="message ${isSuccess ? 'success' : 'error'}">${message}</div>`;
            setTimeout(() => messageDiv.innerHTML = '', 5000);
        }
        
        async function startContainer() {
            showLoading();
            const imageName = document.getElementById('imageInput').value || 'hello-world';
            
            try {
                const response = await fetch('/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({image: imageName})
                });
                
                const data = await response.json();
                showMessage(data.message, data.success);
                updateStatus(data.status);
            } catch (error) {
                showMessage('Error: ' + error.message, false);
            } finally {
                hideLoading();
            }
        }
        
        async function stopContainer() {
            showLoading();
            
            try {
                const response = await fetch('/stop', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                
                const data = await response.json();
                showMessage(data.message, data.success);
                updateStatus(data.status);
            } catch (error) {
                showMessage('Error: ' + error.message, false);
            } finally {
                hideLoading();
            }
        }
        
        async function checkDockerStatus() {
            try {
                const response = await fetch('/docker-info');
                const info = await response.json();
                const dockerStatusDiv = document.getElementById('dockerStatus');
                
                if (info.connected) {
                    dockerStatusDiv.innerHTML = `
                        <div class="status running">
                            Docker Connected<br>
                            Version: ${info.docker_version}<br>
                            Running: ${info.containers_running}
                        </div>`;
                } else {
                    dockerStatusDiv.innerHTML = `
                        <div class="status stopped">
                            Docker Connection Failed<br>
                            ${info.error}
                        </div>`;
                }
            } catch (error) {
                document.getElementById('dockerStatus').innerHTML = 
                    '<div class="status stopped">Cannot reach server</div>';
            }
        }
        
        updateStatus({{ status | tojson }});
        checkDockerStatus();
        
        setInterval(async () => {
            try {
                const response = await fetch('/status');
                const status = await response.json();
                updateStatus(status);
            } catch (error) {
                console.log('Status check failed:', error);
            }
        }, 10000);
    </script>
</body>
</html>'''
    
    with open('templates/index.html', 'w') as f:
        f.write(html)

if __name__ == '__main__':
    if not init_docker():
        print("Docker initialization failed")
        print("Make sure Docker is running")
    
    create_html()
    print("Starting Flask app on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)