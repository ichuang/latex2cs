function add_showhide_ws(the_divname) {
    var divname = the_divname;
    var button_name = `${divname}_button`;
    var btitle;
    var state = "hidden";
    var click = function(){
        if (state=="hidden"){ show();
	}else{ hide();
	}
    }
    var show = function(){
	document.getElementById(divname).style.display = "block";
	document.getElementById(button_name).innerHTML = "Hide " + btitle;
	state = "shown";
    }
    var hide = function(){
	document.getElementById(divname).style.display = "none";
	document.getElementById(button_name).innerHTML = "Show " + btitle;
	state = "hidden";
    }
    var setup = function(){
	document.addEventListener("DOMContentLoaded", setup_now);
    }
    var setup_now = function(){
	if (!document.getElementById(divname)){
	    setTimeout(setup_now, 500);
	    return;
	}
	setup_button();
	setup_hidden_div();
	hide();
    }
    var setup_button = function(){
	var sd = document.getElementById(divname);
	var button = document.createElement("button"); 
	button.style["font-size"] = "18px";
	button.style['border'] = "2px solid";
	button.style['border-color'] = 'blue';
	button.style['border-radius'] = '10px';
	button.id = button_name;
	// button.innerHTML = "Show optional content";
	btitle = sd.getAttribute("description");
	button.innerHTML = btitle;
	button.onclick = click;
	sd.parentElement.insertBefore(button, sd)
    }

    var setup_hidden_div = function(){
	return;
	var sd = document.getElementById(divname)
	var pp = sd.parentElement
	var started = false;
	var tocopy = [];
	for (k = 0; k < pp.childNodes.length; k++){
	    var c = pp.childNodes[k];
	    if (c==sd){ started = true; continue; }
	    if (c.tagName=="A" && c.className=="anchor"){ started = false; continue; }
	    if (started){ tocopy.push(c); }
	}
	tocopy.forEach(function(c){ sd.appendChild(c); });
    }
    console.log(`showhide with divname=${divname}`);
    setup();
    return {setup: setup,
	    setup_now: setup_now,
            click: click}
}
