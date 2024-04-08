import os, requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

import redis
from redis_cache import RedisCache
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from starlette.responses import JSONResponse, Response


load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-pro')


client = redis.from_url(os.getenv("REDIS_URI"), decode_responses=True)
rediscache = RedisCache(redis_client=client)


prompt = f"Write a summary of the current condition of the stock in beginner friendly manner . the summary should be in the form of a story. It should be simple enough to be understood by naive people. the summary must contain some facts with some numerical data from the data. the output should be in markdown format with minimum of 300 words.\
The company information: "

   

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@rediscache.cache(ttl=86400)
def fetch_news(ticker:str):
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": ticker,
        "filter_entities": "true",
        "language": "en",
        "api_token": os.environ["NEWS_API_KEY"]
    }
    news = requests.get(url, params=params).json()['data']
    return news


@rediscache.cache(ttl=86400)
def fetch_summary(ticker:str) -> str:
    try:
        ticker = yf.Ticker(ticker)
        summary = ticker.info

        if 'companyOfficers' in summary:
            del summary['companyOfficers']

        summary = model.generate_content(
            prompt + str(summary),
            generation_config=genai.types.GenerationConfig(
            candidate_count=1,
            max_output_tokens=1500,
            temperature=0.7),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        return summary.text
    
    except requests.exceptions.ConnectionError:
        return None

@rediscache.cache(ttl=3600)
def fetch_general_news():
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "language": "en",
        "api_token": os.environ["NEWS_API_KEY"]
    }
    news = requests.get(url, params=params).json()['data']
    return news


@app.get("/")
async def read_root():
    return "Hello World"

@app.get("/summary/{ticker}")
async def get_summary(ticker:str):
    summary = fetch_summary(ticker)
    if summary is not None: 
        return summary
    else:
        return HTTPException(status_code=404, detail="Summary not found")


@app.get("/news/{ticker}")
async def get_news(ticker:str):
    news = fetch_news(ticker)
    return JSONResponse(news)

@app.get("/general_news")
async def get_general_news():
    news = fetch_general_news()
    return JSONResponse(news)

@app.get("/health")
async def health():
    return "OK"

@app.get("/clear_cache")
async def clear_cache():
    client.flushall()
    return "OK"
