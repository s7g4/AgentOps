from app.api.main import create_app
from app.config.settings import load_settings

app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
