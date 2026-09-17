"""Start the kiosk agent:  .venv\\Scripts\\python run_agent.py"""
from agent import create_agent_app

app = create_agent_app()

if __name__ == "__main__":
    app.run(host=app.config["AGENT_HOST"], port=app.config["AGENT_PORT"], debug=False, threaded=True)
