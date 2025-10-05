const tbl = document.getElementById('eventsTable');
const formEvt = document.getElementById('eventForm');

const evtLatEl = document.getElementById('evt_lat');
const evtLonEl = document.getElementById('evt_lon');
const evtLocLbl = document.getElementById('evt_loc_lbl');

let evtMap=null, evtMarker=null;

function rowHtml(r){
  const temp = r.temp_c==null ? '—' : `${r.temp_c.toFixed(1)} °C`;
  const p = r.precip_mm==null ? '—' : `${r.precip_mm.toFixed(2)} mm`;
  return `
    <tr>
      <td>${r.title}</td>
      <td>${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}</td>
      <td>${r.date}</td>
      <td>${temp}</td>
      <td>${p}</td>
      <td><span class="badge bg-secondary">${r.risk||'Low'}</span></td>
      <td class="text-end">
        <button class="btn btn-sm btn-outline-warning me-2" data-recheck="${r.id}">Recheck</button>
        <button class="btn btn-sm btn-outline-danger" data-del="${r.id}">Delete</button>
      </td>
    </tr>`;
}

async function loadEvents(){
  const r = await fetch('/api/events/list');
  const j = await r.json();
  const arr = j.data || [];
  tbl.querySelector('tbody').innerHTML = arr.map(rowHtml).join('') || `<tr><td colspan="7" class="text-center text-muted">No events yet</td></tr>`;
}

tbl?.addEventListener('click', async (e)=>{
  const idDel = e.target.getAttribute('data-del');
  const idRe = e.target.getAttribute('data-recheck');
  if(idDel){
    if(confirm('Delete this event?')){
      await fetch('/api/events/delete/'+idDel, {method:'DELETE'});
      loadEvents();
    }
  } else if(idRe){
    e.target.disabled = true;
    await fetch('/api/events/recheck/'+idRe, {method:'POST'});
    e.target.disabled = false;
    loadEvents();
  }
});

formEvt?.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const fd = new FormData(formEvt);
  const payload = {
    title: fd.get('title'),
    lat: parseFloat(fd.get('lat')),
    lon: parseFloat(fd.get('lon')),
    date: fd.get('date')
  };
  const r = await fetch('/api/events/create', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const j = await r.json();
  if(j.error){ alert(j.error); return; }
  formEvt.reset();
  // keep last picked coords:
  formEvt.querySelector('input[name="lat"]').value = evtLatEl.value;
  formEvt.querySelector('input[name="lon"]').value = evtLonEl.value;
  loadEvents();
});

function ensureEvtMap(lat,lon){
  if(!evtMap){
    evtMap = L.map('evt_map',{zoomControl:true}).setView([lat,lon],11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',{
      subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'
    }).addTo(evtMap);
    evtMarker = L.marker([lat,lon]).addTo(evtMap);
    evtMap.on('click', (e)=>{
      const {lat,lng} = e.latlng;
      evtMarker.setLatLng([lat,lng]);
      evtLatEl.value = lat.toFixed(4);
      evtLonEl.value = lng.toFixed(4);
      evtLocLbl.textContent = `Lat ${lat.toFixed(4)}, Lon ${lng.toFixed(4)}`;
    });
    setTimeout(()=> evtMap.invalidateSize(), 50);
  }
}

window.addEventListener('DOMContentLoaded', ()=>{
  const lat = parseFloat(evtLatEl.value), lon = parseFloat(evtLonEl.value);
  ensureEvtMap(lat,lon);
  evtLocLbl.textContent = `Lat ${lat.toFixed(4)}, Lon ${lon.toFixed(4)}`;
  loadEvents();
});
