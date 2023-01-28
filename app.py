import streamlit as st
import folium
import json
import http.client, urllib.parse
import os
from streamlit_folium import folium_static
import pandas as pd
import folium.plugins as plugins
import streamlit_analytics
import openai
from st_draggable_list import DraggableList
import requests
from typing import Dict, List, Tuple, Object

COUNTRIES = pd.read_csv('country_codes_updated.csv')
CITIES = pd.read_csv('worldcities.csv')

def show_country_info(country: str) -> None:

  """
  Method to get information about the target country and show it in the application.
 
  Input:
    country (str): name of the country
  Output:
    None
  """

  try:

    res = requests.get(f"https://restcountries.com/v3.1/name/{country}?fullText=true")
    info = res.json()

    col1, col2 = st.columns(2)

    with col1:

      try:
        country_name = info[0]['name']['official']
        st.subheader(f"{country_name}")
      except:
        raise Exception("Do not print information")
      
      try:
        country_capital = info[0]['capital'][0]
        st.markdown(f"- **Capital**: {country_capital}")
      except:
        pass

      try:
        country_currencies = info[0]['currencies']
        text = f"- **Currencies**:"
        for key in country_currencies:
          text += f"\n  - {country_currencies[key]['name']} ({country_currencies[key]['symbol']})"
        st.markdown(text)
      except:
        pass

    with col2:

      try:
        country_flag = info[0]['flags']['png']
        st.image(country_flag)
      except:
        pass
      
  except:
    pass

def generate_itinerary(country: str, first_city: str, last_city: str, num_cities: int) -> str:

  """
  Method to send a request to the GPT model, to generate the itinerary.

  Input:
    country (str): name of the country
    first_city (str): name of the first city to visit (arrival)
    last_city (str): name of the last city to visit (departure)
    num_cities (int): number of cities to visit
  Output:
    text (str): model response, with the format [city1, city2, ...]
  """

  openai.api_key = st.secrets["OPENAI_KEY"]

  ask = f"Do a {num_cities} day travel itinerary through {country}, starting in {first_city} and ending in {last_city}. Return with this format: [city1, city2, ...]"
  response = openai.Completion.create(
    model="text-davinci-003",
    prompt=ask,
    temperature=0.9,
    max_tokens=150,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0.6,
    stop=[" Human:", " AI:"]
    )

  text = response['choices'][0]['text']

  return text

def get_coordinates(country: str, city: str) -> List[float]:

  """  
  Method to get the geographical coordinates of a city in a country.
  
  Input:
    country (str): name of the country
    city (str): name of the city
  Output:
    coordinates (list): list with the two coordinates of the city
  """

  try:
    code = COUNTRIES.loc[COUNTRIES['country']==country]['code'].item()
  except:
    raise RuntimeError("Invalid country name!")

  conn = http.client.HTTPConnection('api.positionstack.com')

  params = urllib.parse.urlencode({
      'access_key': st.secrets["COUNTRIES_KEY"],
      'query': city,
      'country': code, 
      'limit': 1,
      })

  conn.request('GET', '/v1/forward?{}'.format(params))

  res = conn.getresponse()
  data = res.read().decode('utf-8')
  json_data = json.loads(data)
  coordinates = {k: json_data['data'][0][k] for k in ('latitude', 'longitude')}
  return list(coordinates.values())

def process_itinerary(text: str) -> Tuple(List[Dict], List[List[float]]):

  """
  Method to process the response of the GPT model into locations of the itinerary.

  Input:
    text (str): string with the response of the GPT model
  Output:
    locations (list): list of dictionaries with the format {'name': <city name>, 'coordinates': <coordinates>}
    all_coord (list): list with the coordinates of all cities
  """

  text = text.replace("[", "").replace("]", "").split(",")
  city_list = [t.replace("'", "").strip() for t in text]

  all_coord = []
  locations = []
  for city in city_list:
    try:
      coord = get_coordinates(country, city)
    except Exception as error:
      print(error)
      continue
    all_coord.append(coord)
    loc = {'name': city, 'coordinates': coord}
    print(f"   > {city} ({coord})")
    locations.append(loc)

  return locations, all_coord

def plot_locations(locations: List[Dict], avg_coordinates: List[float]) -> Object:

  """
  Method to plot the locations into a folium map.

  Input:
    locations (list): list of dictionaries with the format {'name': <city name>, 'coordinates': <coordinates>}
    avg_coordinates (list): list with the average coordinates of all locations
  Output:
    map (folium map object): folium map
  """

  col_hex = ["#FF4B4B"]*len(locations)

  if locations[0] == locations[-1]:
    same_first_last = True
  else:
    same_first_last = False

  map = folium.Map(location=avg_coordinates, zoom_start=5)
  folium.TileLayer('cartodbpositron').add_to(map)

  for i, location in enumerate(locations):

    if i == len(locations)-1 and same_first_last:
      continue

    lat, lon = location['coordinates']
    name = location['name']

    folium.Marker(
        location=[lat, lon],
        popup=name,
        icon=plugins.BeautifyIcon(
                         icon="arrow-down", icon_shape="marker",
                         number=i+1,
                         border_color= col_hex[i],
                         background_color=col_hex[i]
                     )
    ).add_to(map)

  return map

# START OF THE APP -----------------------------------------------------------------------------------------------------------

streamlit_analytics.start_tracking()

st.title("GPT Travel Guide")
st.write("The first version of a travel guide based on a Generative Pre-trained Transformer, the same technology behind chatGPT. For now, it is only configured to generate itinerarys for single countries.")

if 'count' not in st.session_state:
	st.session_state.count = 0

if st.session_state.count == 0:
  st.session_state.disabled = False

country = st.selectbox("Country", COUNTRIES['country'].tolist(), index=COUNTRIES[COUNTRIES['country']=="Portugal"].index.item(), disabled=st.session_state.disabled)
col1, col2, col3 = st.columns(3)
first_city = col1.selectbox("First city", CITIES.loc[CITIES['country']==country]['city'].tolist(), disabled=st.session_state.disabled)
last_city = col2.selectbox("Last city", CITIES.loc[CITIES['country']==country]['city'].tolist(), disabled=st.session_state.disabled)
num_days = col3.number_input("Number of cities", value=5, format="%i", disabled=st.session_state.disabled, min_value=3)


col1, col2, col3, _, = st.columns(4)
submit = col1.button("Generate itinerary")
clear = col2.button("Clear")

if submit:
  if st.session_state.count != 0:
    col1.markdown("**Clear first!**")
  else:
    st.session_state.count = 1
    st.experimental_rerun()
    
if clear:
  st.session_state.count = 0
  st.session_state.disabled = False
  st.experimental_rerun()

if st.session_state.count > 0:

    st.session_state.disabled = True

    show_country_info()

    code = f"{country}_{first_city}_{last_city}_{num_days}"

    if os.path.exists(f"{code}.csv"):

      print("Found existing itinerary!")

      locations = pd.read_csv(f"{code}.csv")
      locations = locations.to_dict('records')

      locations = [{"name": d["name"], "coordinates": json.loads(d["coordinates"])} for d in locations]
      all_coord = [d['coordinates'] for d in locations]

      locations_df = pd.DataFrame(locations)

    else:

      print("Will generate new itinerary!")

      text = generate_itinerary(country, first_city, last_city, num_days)
      print(text)

      locations, all_coord = process_itinerary(text)
      locations_df = pd.DataFrame(locations)
      if len(locations_df) > 0:
        locations_df.to_csv(f"{code}.csv", index=False)

    if len(locations) == 0 or len(locations_df) == 0:
   
      st.write("")
      st.write("Sorry, it was not possible to generate the itinerary...")
      st.write("You can always click clear and try another!")
   
    else:

      st.subheader(f"{num_days} cities to visit in {country}")
      st.write("If you are in a computer, you can drag and drop the different locations to re-order and see on the map.")

      slist = DraggableList(locations, key="name")

      locations_df['longitude'] = locations_df['coordinates'].apply(lambda x: x[1])
      locations_df['latitude'] = locations_df['coordinates'].apply(lambda x: x[0])
    
      avg_coordinates = list(map(lambda x: sum(x)/len(all_coord), zip(*all_coord)))

      try:
        map = plot_locations(slist, avg_coordinates)
      except:
        map = plot_locations(locations, avg_coordinates)

      folium_static(map)

streamlit_analytics.stop_tracking(unsafe_password=st.secrets["ANALYTICS_KEY"])