import os
from flask_app import app

if __name__ == "__main__":
    # Get port from environment variable (Hugging Face uses 7860)
    port = int(os.environ.get("PORT", 7860))
    
    # Run the app
    app.run(host="0.0.0.0", port=port, debug=False) 