const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalized=value=>String(value).trim().toLocaleLowerCase();
export function filterVendors(names,query=''){const words=normalized(query).split(/\s+/).filter(Boolean);return [...new Set(names)].filter(name=>words.every(word=>normalized(name).includes(word))).sort((a,b)=>a.localeCompare(b));}
export function createVendorPicker(names,{onChange=()=>{}}={}){
  const state={query:'',selected:'',active:-1,open:true};
  const matches=()=>filterVendors(names,state.query).slice(0,12);
  function choose(name){if(!names.includes(name))return false;Object.assign(state,{query:name,selected:name,active:-1,open:false});onChange(state);return true;}
  return {state,matches,choose,input(value){Object.assign(state,{query:value,selected:'',active:-1,open:true});onChange(state);},
    setNames(value){names=value;if(state.selected&&!names.includes(state.selected)){state.selected='';state.open=true;}},
    key(key){const options=matches();if(key==='Escape'){if(!state.open)return false;state.open=false;onChange(state);return true;}
      if(['ArrowDown','ArrowUp'].includes(key)){state.open=true;state.active=options.length?(state.active<0?(key==='ArrowDown'?0:options.length-1):(state.active+(key==='ArrowDown'?1:-1)+options.length)%options.length):-1;onChange(state);return true;}
      if(key==='Enter'){if(state.open&&state.active>=0)choose(options[state.active]);else if(state.open&&options.length===1)choose(options[0]);return true;}return false;}};
}
export function vendorOptionsHTML(names,state={query:'',open:true,active:-1}){
  const options=filterVendors(names,state.query).slice(0,12);
  return state.open?(options.length?options.map((name,i)=>`<li role="option" id="vendor-option-${i}" aria-selected="${i===state.active}"><button type="button" tabindex="-1" data-action="vendor-picker-select" data-vendor="${esc(name)}">${esc(name)}</button></li>`).join(''):'<li class="vendor-no-results" role="option" aria-disabled="true">No saved vendors match. Try another name.</li>'):'';
}
export function vendorPickerHTML(names,state={query:'',selected:'',active:-1,open:true}){
  return `<div class="vendor-picker"><label class="field">BILL vendor<input id="vendor-search" type="search" role="combobox" autocomplete="off" aria-autocomplete="list" aria-expanded="${state.open}" aria-controls="vendor-options" ${state.active>=0?`aria-activedescendant="vendor-option-${state.active}"`:''} placeholder="Type to find a vendor…" value="${esc(state.query)}"></label><input id="statement-bill-vendor" type="hidden" value="${esc(state.selected)}"><ul id="vendor-options" role="listbox" aria-label="Matching BILL vendors" ${state.open?'':'hidden'}>${vendorOptionsHTML(names,state)}</ul><small>Type any part of the name. Choose a result, then confirm below.</small><button class="button" data-action="vendor-choose" ${state.selected?'':'disabled'}>Use this vendor</button></div>`;
}
