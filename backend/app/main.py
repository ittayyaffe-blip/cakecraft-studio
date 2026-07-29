from fastapi import FastAPI

app = FastAPI(
    title="CakeCraft Studio API",
    version="0.1.0"
)


@app.get("/")
def root():
    return {
        "message": "Welcome to CakeCraft Studio!"
    }
    