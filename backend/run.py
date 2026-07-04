import uvicorn

if __name__ == "__main__":
    # reload=True so backend code changes take effect without restarting the platform
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
