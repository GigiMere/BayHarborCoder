// ---- Helpers
const SOLO_ORDER = ['sunny','partly_cloudy','cloudy','light_rain','rainy'];
function condDistance(a,b){
  const i=SOLO_ORDER.indexOf(a), j=SOLO_ORDER.indexOf(b);
  if(i<0||j<0) return 2;
  return Math.abs(i-j);
}
async function getJSON(u){ const r=await fetch(u); return r.json(); }
function iconFile(cond){
  const map = {
    sunny:'sunny.png',
    partly_cloudy:'partly_cloudy.png',
    cloudy:'cloudy.png',
    light_rain:'light_rain.png',
    rainy:'rainy.png'
  };
  return '/static/img/icons/' + (map[cond] || 'cloudy.png');
}

// ---- DOM
const soloName   = document.getElementById('solo_name');
const soloNext   = document.getElementById('solo_next');
const soloCity   = document.getElementById('solo_city');
const soloImg    = document.getElementById('solo_img');
const soloMapDiv = document.getElementById('solo_map');
const soloCoins  = document.getElementById('solo_coins');
const soloResult = document.getElementById('solo_result');
const soloTruthPng = document.getElementById('solo_truth_png');
const soloTruthTxt = document.getElementById('solo_truth_txt');
const soloPoints   = document.getElementById('solo_points');

let soloMap=null, soloMarker=null, soloCityData=null;

function ensureSoloMap(lat,lon){
  if(!soloMap){
    soloMap = L.map(soloMapDiv,{zoomControl:true}).setView([lat,lon],11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',{
      subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'
    }).addTo(soloMap);
    soloMarker = L.marker([lat,lon]).addTo(soloMap);
  } else {
    soloMap.setView([lat,lon],11);
    soloMarker.setLatLng([lat,lon]);
  }
}

async function refreshCoins(){
  const name = (soloName.value || 'Player').trim().slice(0,30);
  const j = await getJSON(`/api/coins/get?name=${encodeURIComponent(name)}`);
  soloCoins.textContent = j.coins ?? 0;
}

soloNext?.addEventListener('click', async ()=>{
  const cities = await getJSON('/api/cities');
  const arr = cities.data || [];
  const pick = arr[Math.floor(Math.random()*arr.length)];
  soloCityData = pick;
  soloCity.textContent = pick.name;

  // city image – show immediately, and if not found show a neutral fallback
  soloImg.onerror = ()=>{ soloImg.onerror = null; soloImg.src = '/static/img/cities_us/new_york.png'; };
  soloImg.src = pick.img;

  ensureSoloMap(pick.lat, pick.lon);
  soloResult.classList.add('d-none');
});

document.querySelectorAll('.sguess').forEach(btn=>{
  btn.addEventListener('click', async ()=>{
    if(!soloCityData) return;
    const guess = btn.dataset.v;
    const truth = await getJSON(`/api/today?lat=${soloCityData.lat}&lon=${soloCityData.lon}`);
    const truthCond = truth.condition || 'sunny';
    const dist = condDistance(guess, truthCond);
    const award = dist===0 ? 3 : (dist===1 ? 1 : 0);

    soloTruthPng.onerror = ()=>{ soloTruthPng.onerror=null; soloTruthPng.src='/static/img/icons/Draw_cloudy.png'; };
    soloTruthPng.src = iconFile(truthCond);

    soloTruthTxt.textContent = truthCond.replace('_',' ');
    soloPoints.textContent = award;

    const name = (soloName.value || 'Player').trim().slice(0,30);
    await fetch('/api/coins/add', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name, delta: award }) });
    await refreshCoins();
    soloResult.classList.remove('d-none');
  });
});

window.addEventListener('DOMContentLoaded', refreshCoins);
