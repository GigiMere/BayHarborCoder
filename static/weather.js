const form = document.getElementById('weatherForm');
const alertBox = document.getElementById('alertBox');
const todayPng = document.getElementById('todayPng');
const todayTemp = document.getElementById('todayTemp');
const latEl = document.getElementById('lat');
const lonEl = document.getElementById('lon');
const locLabel = document.getElementById('locLabel');

let map, marker;

function showError(msg){
  if(!msg){ alertBox.classList.add('d-none'); alertBox.textContent=''; return; }
  alertBox.classList.remove('d-none'); alertBox.textContent = msg;
}

function iconFile(cond){
  const m = {
    sunny:'sunny.png',
    partly_cloudy:'partly_cloudy.png',
    cloudy:'cloudy.png',
    light_rain:'light_rain.png',
    rainy:'rainy.png'
  };
  return '/static/img/icons/' + (m[cond] || 'cloudy.png');
}

function ensureMap(lat,lon){
  if(map) return;
  map = L.map('map', { zoomControl: true }).setView([lat, lon], 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
    subdomains: 'abcd', maxZoom: 19, attribution: '© OpenStreetMap © CARTO'
  }).addTo(map);
  marker = L.marker([lat, lon], {draggable:false}).addTo(map);

  map.on('click', (e)=>{
    const {lat, lng} = e.latlng;
    latEl.value = lat.toFixed(4);
    lonEl.value = lng.toFixed(4);
    marker.setLatLng([lat,lng]);
    loadDay(document.getElementById('date').value);
  });

  setTimeout(()=> map.invalidateSize(), 50);
}

async function loadDay(dateISO){
  showError('');
  const lat = parseFloat(latEl.value||'40.7128');
  const lon = parseFloat(lonEl.value||'-74.0060');
  locLabel.textContent = `Lat ${lat.toFixed(4)}, Lon ${lon.toFixed(4)}`;

  try{
    const r = await fetch(`/api/weather/day?lat=${lat}&lon=${lon}&date=${encodeURIComponent(dateISO)}`);
    const d = await r.json();
    if(d.error){ showError(d.error); todayTemp.textContent='—'; return; }

    todayPng.onerror = ()=>{ todayPng.onerror=null; todayPng.src='/static/img/icons/Draw_cloudy.png'; };
    todayPng.src = iconFile(d.condition);

    todayTemp.textContent = (d.temp_c==null ? '—' : Math.round(d.temp_c) + '°');

    if(map){
      marker.setLatLng([lat,lon]);
      map.setView([lat,lon], map.getZoom());
    }
  }catch{
    showError('Network error.');
  }
}

window.addEventListener('DOMContentLoaded', ()=>{
  const dateEl = document.getElementById('date');
  dateEl.value = new Date().toISOString().slice(0,10);
  ensureMap(parseFloat(latEl.value), parseFloat(lonEl.value));
  loadDay(dateEl.value);
});

form?.addEventListener('submit', (e)=>{
  e.preventDefault();
  loadDay(document.getElementById('date').value);
});
