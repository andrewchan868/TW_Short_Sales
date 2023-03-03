from typing import List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import asyncio
import numpy as np
import copy
import json
import pandas as pd
import threading
import time
from helper import get_logger
# flask app
from flask import Flask, redirect
from flask import render_template, request

# website endpoints
host_name = "0.0.0.0"
port = 5000 
app = Flask(__name__)

# config setup
with open('config/config.json', 'r') as f:
    config = json.load(f)
    
url = config['tw_stock_short_quota']
delay = config['delay']
pages_flap = config['page_flap']
sma_tf = config['sma_timeframe']
threshold_percent = config['threshold_percent']
watch_stock_list = config['watch_list']
breaking_news = config['breaking_news']
news_frequency = config['news_frequency']
timeout = 5
s=Service(ChromeDriverManager().install())

# global variables for caching
stocks_dict = {}
sma_free_shares_SBL_price_list = list()
df_sma_diff_current_price = pd.DataFrame()
df_sma_diff_current_price_daystart = pd.DataFrame()
index_dict = dict()
taipei_times_news = {"1":'', "2":'', "3":'', "4":'', "5":''}
TVBS_news = {"1":'', "2":'', "3":'', "4":'', "5":''}

# SMA timeframe
sma_tf = int(sma_tf)

# parameters to control program flow
program_start = True

def collect_data(driver, timeout):
    global stocks_dict, index_dict
    # function to actually scrap the data on the page
    try:
        stockTable = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//*[@id='sblCapTable']/tbody")))

        stocks = WebDriverWait(stockTable, timeout).until(
            EC.presence_of_all_elements_located((By.TAG_NAME, "tr")))  

        
        for stock in stocks:
            stock_data_dict = {
            "stock_code":str, 
            "free_shares_SBL":float,
            "last_modify_time":str,
            }
            stock_code = WebDriverWait(stock, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//td[2]")))
            free_shares_SBL = WebDriverWait(stock, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//td[3]")))
            last_modify_time = WebDriverWait(stock, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//td[4]")))
            if not (int(free_shares_SBL.text.replace(',','')) <= 0):
                num_float = float(free_shares_SBL.text.replace(',',''))
                stock_data_dict["stock_code"] = stock_code.text
                stock_data_dict["free_shares_SBL"] = float(f'{num_float:.2f}')
                stock_data_dict["last_modify_time"] = last_modify_time.text
                stocks_dict[stock_data_dict["stock_code"]] = stock_data_dict
        
        # get index figures
        news = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//*[@id='news']")))
        indexList = WebDriverWait(news, timeout).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "form-wrapper")))
        
        # special case for the first index
        index_dict[indexList[1].text.split()[0]] = dict()
        index_dict[indexList[1].text.split()[0]]['name']  = indexList[1].text.split()[0]
        index_dict[indexList[1].text.split()[0]]['price']  = indexList[1].text.split()[2]
        index_dict[indexList[1].text.split()[0]]['change']  = indexList[1].text.split()[10][1:-1]

        for index in indexList[2:]:
            index_name = index.text.split()[0]
            price = index.text.split()[1]
            change = index.text.split()[9][1:-1]
            index_dict[index_name] = dict()
            index_dict[index_name]['name'] = index_name
            index_dict[index_name]['price'] = price
            index_dict[index_name]['change'] = change
        
    finally:
        print("finished page")
        #get_logger().info("finished page")


def calculate_diff_SMA_price():
    global df_sma_diff_current_price, sma_free_shares_SBL_price_list, program_start, df_sma_diff_current_price_daystart
    # function to calculate differences of last price with SMA
    # get the very first quota since program start
    if program_start:
        df_sma_diff_current_price_daystart['day_start'] = copy.deepcopy(sma_free_shares_SBL_price_list[0]['free_shares_SBL'])
        program_start = False

    # calculate SMA price
    data_point_len = len(sma_free_shares_SBL_price_list)
    df_sma_free_shares_SBL = copy.deepcopy(sma_free_shares_SBL_price_list[0])
    for sma_free_shares_SBL_price in sma_free_shares_SBL_price_list[1:]:
        df_sma_free_shares_SBL = df_sma_free_shares_SBL.set_index("stock_code").add(sma_free_shares_SBL_price.set_index("stock_code"), fill_value=0).reset_index()
    df_sma_free_shares_SBL.rename(columns = {'free_shares_SBL':'free_shares_SBL_sum'}, inplace = True)
    df_sma_free_shares_SBL['free_shares_SBL_sma'] = df_sma_free_shares_SBL['free_shares_SBL_sum']/data_point_len
    df_sma_free_shares_SBL = df_sma_free_shares_SBL.set_index('stock_code')
    # calculate the Differences
    current_free_shares_SBL_price = copy.deepcopy(sma_free_shares_SBL_price_list[0])
    df_sma_diff_current_price = copy.deepcopy(sma_free_shares_SBL_price_list[0])
    df_sma_diff_current_price['day_start'] = copy.deepcopy(df_sma_diff_current_price_daystart['day_start'])
    df_sma_diff_current_price['difference'] = current_free_shares_SBL_price['free_shares_SBL'] / df_sma_free_shares_SBL['free_shares_SBL_sma']
    df_sma_diff_current_price['free_shares_SBL_SMA'] = df_sma_free_shares_SBL['free_shares_SBL_sma']
    # sort by ascending order
    df_sma_diff_current_price = df_sma_diff_current_price.sort_values('difference') 
    df_sma_diff_current_price = df_sma_diff_current_price.round(4)
    print(df_sma_diff_current_price)

async def output_csv():
    global df_sma_diff_current_price 
    while(True):
        df_sma_diff_current_price.to_csv('df_sma_diff_current_price.csv')
        print("data are saved")
        await asyncio.sleep(20)

async def grap_news():
    global breaking_news, news_frequency
    while(True):
        try:
            driver = webdriver.Chrome(service=s)
            driver.set_window_position(-10000,0) #put the window aside
            # grap taipei_times
            driver.get(breaking_news["taipei_times"])
            for i in range(1,6):
                popular_new = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, f"//*[@id='read']/ul/li[{i}]")))
                taipei_times_news[str(i)] = popular_new.text[2:]
                      
            # grap TVBS
            driver.get(breaking_news["TVBS"])
            for i in range(1,6):
                popular_new = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, f"/html/body/div[1]/main/div/article/div[2]/div[2]/ul/li[{i}]")))
                TVBS_news[str(i)] = popular_new.text
            await asyncio.sleep(0)
        except:
            driver.quit()
            #get_logger("exceptin cause")
            print("exceptin cause")
            continue

async def main():
    global sma_free_shares_SBL_price_list
    sma_start_time = time.time()  # remember when we started
    while(True):
        try:
            driver = webdriver.Chrome(service=s)
            driver.set_window_position(-10000,0) #put the window aside
            start_time = time.time()
            driver.get(url)
            #select 100 stocks display
            selector = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, ".//*[@id='prePage']/option[4]")))
            selector.click()
            #check page is displayed successfully
            element_present = EC.presence_of_element_located((By.ID, 'sblCapTable'))
            WebDriverWait(driver, timeout).until(element_present)
            if element_present is not None:
                collect_data(driver, timeout)

            for i in range(pages_flap):
                pagesList = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "pagination")))
                pagesButtons = WebDriverWait(pagesList[0], timeout).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
                if i > 0:
                    pagesButtons = pagesButtons[2:] # remove the two buttons of "First Page" and "prev"
                page = pagesButtons[i]
                page.click()
                #check page is displayed successfully
                element_present = EC.presence_of_element_located((By.ID, 'sblCapTable'))
                WebDriverWait(driver, timeout).until(element_present)
                if element_present is not None:
                    collect_data(driver, timeout)
                
            pagesButtons = None
            driver.quit()
            
            timeElapsed = "time elpase for one whole loop: " + str(time.time() - start_time)
            #get_logger().info(timeElapsed)
            print(timeElapsed)
            timeElapsed = None

            if len(stocks_dict) != 0:
                df_stocks = pd.DataFrame(stocks_dict)
                df_stocks = df_stocks.transpose()
                df_free_shares_SBL = df_stocks[['stock_code', 'free_shares_SBL']]
                    
            if (time.time() - sma_start_time) < sma_tf:
                # accumulate prices for calculating SMA
                sma_free_shares_SBL_price_list.append(df_free_shares_SBL)
            else:
                # subsequent addition of new prefices
                sma_free_shares_SBL_price_list.pop(0) # drop the first element
                sma_free_shares_SBL_price_list.append(df_free_shares_SBL) # add the new data at the end
                # calculate diff by data collected
                calculate_diff_SMA_price()
            await asyncio.sleep(0)
        except:
            driver.quit()
            #get_logger("exceptin cause")
            print("exceptin cause")
            continue


# flask web
@app.route('/')
def test():
    return 'Hello, world'

@app.route('/index_json')
def index_json():
    global index_dict
    index_json = json.loads(json.dumps(index_dict))
    return index_json

@app.route('/data_json')
def diff_data_json():
    global df_sma_diff_current_price, threshold_percent
    if not df_sma_diff_current_price.empty:
        df_meet_threshold = copy.deepcopy(df_sma_diff_current_price[df_sma_diff_current_price['difference'] <= float(threshold_percent)])
        df_meet_threshold = df_meet_threshold.sort_values('difference')
        df_meet_threshold['difference'] = df_meet_threshold['difference'] - 1
    else:
        df_meet_threshold = pd.DataFrame()
    json_list = json.loads(json.dumps(df_meet_threshold.iloc[:15].transpose().to_dict()))
    return json_list

@app.route('/taipei_times_news')
def taipei_times_news_json():
    global taipei_times_news
    json_list = json.loads(json.dumps(taipei_times_news))
    return json_list


@app.route('/TVBS_news')
def TVBS_news_json():
    global TVBS_news
    json_list = json.loads(json.dumps(TVBS_news))
    return json_list
    

@app.route('/short_quota')
def index():
    global df_sma_diff_current_price, threshold_percent, index_dict
    diff_data = diff_data_json()
    index_data = index_json()
    taipei_times_news_data = taipei_times_news_json()
    TVBS_news_data = TVBS_news_json()
    return render_template(
        'index.html',
        df_sma_diff_current_price=diff_data,
        index_data = index_data,
        index_data_columns = index_data.keys(),
        columns = df_sma_diff_current_price.columns,
        threshold_percent = threshold_percent,
        taipei_times_news_data = taipei_times_news_data,
        TVBS_news_data = TVBS_news_data, 
        )

@app.route('/threshold',methods=['POST', 'GET'])
def result():
    global threshold_percent, df_sma_diff_current_price
    output = request.form.to_dict()
    threshold_percent = float(output["value"])
    return redirect("/short_quota")


@app.route('/watch_list')
def watch_list():
    global watch_stock_list
    watch_stock_list_dict = dict.fromkeys(watch_stock_list, "stock")
    watch_list_json = json.loads(json.dumps(watch_stock_list_dict))
    return watch_list_json


if __name__ == "__main__":
    # serve the web in another thread
    threading.Thread(target=lambda: app.run()).start()
    coroutines = [main(), grap_news(), output_csv()]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.gather(*coroutines))







