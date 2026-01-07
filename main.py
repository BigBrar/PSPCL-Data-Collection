import httpx
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import os

load_dotenv() # Loads .env into environment


class PunjabPowerSupply:
    def __init__(self):
        self.project_url = os.getenv('SUPABASE_PROJECT_URL')
        self.api_key = os.getenv('SUPABASE_API_KEY')
        self.pspcl_token_id = os.getenv('PSPCL_TOKEN_ID')
        self.supabase: Client = create_client(self.project_url, self.api_key)

        self.default_powercut_url = f"https://distribution.pspcl.in/returns/module.php?to=NCC.apiGetOfflineFeedersinSD&token={self.pspcl_token_id}&sdid="
        self.json_file = "district+divisions+subdivisions.json"
        self.current_power_status = []
        if self.pspcl_token_id:
            print(f"DEBUG: Token ID is {self.pspcl_token_id[:5]}***")
        else:
            print("❌ ERROR: PSPCL_TOKEN_ID is missing!")
        
        # Set to 20 to stay within server 'comfort zones'
        self.limit = asyncio.Semaphore(40)

        with open(self.json_file,'r')as file:
            self.districts = json.load(file)
        
        with open("districts.json",'r')as file:
            self.districts_with_lat_lon = json.load(file)

    
    async def fetch_weather_for_districts(self):
        """Standalone async function to fetch weather for all districts in parallel (max 10 at a time)"""
        weather_map = {}
        
        # Helper to fetch a single district's weather
        async def fetch_one_district(client, district):
            async with self.limit: # Use the same 10-request limit
                lat, lon = district['lat'], district['lon']
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,weather_code,wind_speed_10m&forecast_days=1"
                try:
                    resp = await client.get(url, timeout=15)
                    if resp.status_code != 200:
                        return district['id'], None
                    
                    data = resp.json().get('current')
                    if not data: return district['id'], None

                    return district['id'], {
                        "temp": data['temperature_2m'],
                        "precip": data['precipitation'],
                        "wind": data['wind_speed_10m'],
                        "wmo_code": data['weather_code']
                    }
                except Exception as e:
                    print(f"⚠️ Weather failed for {district['name']}: {repr(e)}")
                    return district['id'], None

        print(f"🌤 Fetching weather for {len(self.districts_with_lat_lon)} districts...")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Create all tasks
            tasks = [fetch_one_district(client, d) for d in self.districts_with_lat_lon]
            # Execute them in parallel (obeying the self.limit semaphore)
            results = await asyncio.gather(*tasks)
            
            # Map results to the weather_map dict
            for dist_id, data in results:
                weather_map[dist_id] = data
                
        return weather_map

    async def fetch_status_per_subdivision(self, client, subdivision_id, district_weather, retries=3):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        for attempt in range(retries):
            async with self.limit:
                try:
                    resp = await client.get(f"{self.default_powercut_url}{subdivision_id}", headers=headers, timeout=20)
                    if resp.status_code != 200:
                        if attempt < retries - 1: continue
                        return

                    text = resp.text
                    if '"status":"ok"' in text and '"reason":"All seems OK"' in text:
                        self.current_power_status.append({
                            'id': subdivision_id, 'status': 'power_running',
                            'checked_on': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                            'temperature': district_weather['temp'] if district_weather else None,
                            'precipitation': district_weather['precip'] if district_weather else None,
                            'wind_speed': district_weather['wind'] if district_weather else None,
                            'wmo_code': district_weather['wmo_code'] if district_weather else None
                        })
                        return 
                    elif '"feeder"' in text:
                        print(f'⚡ Power cut at subdivision: {subdivision_id}')
                        self.current_power_status.append({
                            'id': subdivision_id, 'status': text, 
                            'checked_on': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                            'temperature': district_weather['temp'] if district_weather else None,
                            'precipitation': district_weather['precip'] if district_weather else None,
                            'wind_speed': district_weather['wind'] if district_weather else None,
                            'wmo_code': district_weather['wmo_code'] if district_weather else None
                        })
                        return 
                except Exception as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                        continue
                    print(f"❌ Permanent Failure for {subdivision_id}: {repr(e)}")
    
    # Get district details from subdivision ID
    async def get_subdivision_info(self, target_id):
        with open(self.json_file, 'r') as f:
            districts = json.load(f)
        
        for district in districts:
            # Some divisions might not have the 'subdivisions' key yet
            for division in district.get('divisions', []):
                for sub in division.get('subdivisions', []):
                    if sub['id'] == target_id:
                        return {
                            "id": district['id'],
                            "district": district['name'],
                            "division": division['name'],
                            "subdivision": sub['name']
                        }
        
        return "Subdivision ID not found."
    

    async def parse_current_power_response(self):
        new_json_data = []
        for item in range(len(self.current_power_status)):
            if self.current_power_status[item]['status'] != 'power_running':
                # print(f'ITEM = {item}')
                # print(self.current_power_status[item])
                status = self.current_power_status[item]['status']
                str_data = status[status.find('(')+1:].rpartition(')')[0]
                unparsed_json_data = json.loads(str_data)
                for i in range(len(json.loads(str_data))):
                    # print(json_data[f'{i}'])
                    current_data = {}
                    current_data['subdivision_id'] = self.current_power_status[item]['id']
                    current_data['checked_on'] = self.current_power_status[item]['checked_on']
                    current_data['power_available'] = False
                    current_object = unparsed_json_data[f'{i}']
                    current_data['subdivision'] = current_object['subdivision']
                    current_data['feeder'] = current_object['feeder']
                    current_data['outage_type'] = current_object['cat']
                    current_data['start_time'] = current_object['starttime']
                    current_data['end_time'] = current_object['endtime']
                    current_data['temperature'] = self.current_power_status[item]['temperature']
                    current_data['precipitation'] = self.current_power_status[item]['precipitation']
                    current_data['wind_speed'] = self.current_power_status[item]['wind_speed']
                    current_data['weather_code'] = self.current_power_status[item]['wmo_code']
                    current_data['je'] = current_object['je']
                    current_data['areas_affected'] = current_object['areasaffected']

                    # print(current_data)
                    new_json_data.append(current_data)
            elif self.current_power_status[item]['status'] == 'power_running':
                current_data = {}
                current_data['subdivision_id'] = self.current_power_status[item]['id']
                current_data['checked_on'] = self.current_power_status[item]['checked_on']
                current_data['temperature'] = self.current_power_status[item]['temperature']
                current_data['precipitation'] = self.current_power_status[item]['precipitation']
                current_data['wind_speed'] = self.current_power_status[item]['wind_speed']
                current_data['weather_code'] = self.current_power_status[item]['wmo_code']
                current_data['power_available'] = True
                new_json_data.append(current_data)

        # print(f'New json data: {new_json_data}')

        self.current_power_status = new_json_data

    """ Function to save report LOCALLY using JSON """
    # async def save_current_report(self):
    #     with open('unfiltered_status.json', 'w') as file:
    #         json.dump(self.current_power_status, file)
    #     await self.parse_current_power_response()
    #     with open('current_power_status_report.json', 'w') as file:
    #         json.dump(self.current_power_status, file)
    #         # file.write(self.current_power_status)
    #     print("SAVED!!")

    
    """ Function to save report on CLOUD using SUPABASE"""
    async def save_current_report(self):
        # 1. Structure the data using your parser
        # This turns messy API data into the clean list of dictionaries we discussed
        await self.parse_current_power_response()

        if not self.current_power_status:
            print("No data found to upload.")
            return

        # 2. Sync to Supabase
        print(f"Syncing {len(self.current_power_status)} subdivisions to the cloud...")
        try:
            # We pass the whole list at once (Bulk Insert)
            # Supabase matches the keys in your dictionaries to your table columns
            self.supabase.table("power_logs").insert(self.current_power_status).execute()
            print("✅ CLOUD SYNC COMPLETE!!")
        except Exception as e:
            print(f"❌ CLOUD SYNC FAILED: {e}")


    async def fetch_for_all(self):
        self.current_power_status=[]

        # 1. Get the weather data first
        weather_data = await self.fetch_weather_for_districts()

        limits = httpx.Limits(max_keepalive_connections=40, max_connections=80)

        async with httpx.AsyncClient(
            verify=False, 
            timeout=httpx.Timeout(20.0, connect=40.0), 
            limits=limits,
            follow_redirects=True
        ) as client:
            tasks = []
            for district in self.districts:
                # no_districts+=1
                district_weather = weather_data.get(district['id'])
                for division in district['divisions']:
                    # no_divisions+=1
                    # print(division)
                    # break
                    try:
                        for subdivision in division['subdivisions']:
                            tasks.append(self.fetch_status_per_subdivision(client, subdivision['id'], district_weather) )
                    except Exception as e:
                        pass
                    # print("ERROR ",e)
                    # print(division)
            
            await asyncio.gather(*tasks)
            checked = len(self.current_power_status)
            outages = sum(1 for x in self.current_power_status if x['status'] != 'power_running')
            
            print(f"\n📊 FINAL STATS:")
            print(f"✅ Successful Checks: {checked}/422")
            print(f"❌ Failed (even after retries): {422 - checked}")
            print(f"⚡ Outages Detected: {outages}")
            # print(f"No. of subdivisions facing power cuts currently = {len(self.current_power_status)}")
            print('saving results !!!')
            await self.save_current_report()
            print("DONE")


# Add this at the VERY end of your main.py
if __name__ == "__main__":
    # 1. Create the object
    bot = PunjabPowerSupply()
    
    # 2. Run the main fetching function
    # This will trigger fetch -> parse -> save_to_supabase
    import asyncio
    asyncio.run(bot.fetch_for_all())




