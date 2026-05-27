from fastapi import FastAPI

app = FastAPI(name="WatchAgent: Weather Monitor & AI Assistant")


# Health check endpoint
@app.get("/health")
def health_check():
    pass

# Readings endpoint
@app.get("/readings")
def get_readings(city: str = Query(default="Ottawa"), limit: int = Query(default=50)):
    pass

# Events endpoint
@app.get("/events")
def get_events(city: str = Query(default="Ottawa"), limit: int = Query(default=50)):
    pass

