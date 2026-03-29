function fetchTextSync(url) {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, false);
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 300) {
        return xhr.responseText;
    }
    return null;
}

var footer = document.querySelector(".footer");
if (footer) {
    footer.remove();
}

document.querySelectorAll('link[rel="stylesheet"]').forEach(function(link) {
    var cssText = fetchTextSync(link.href);
    if (cssText) {
        var style = document.createElement("style");
        style.type = "text/css";
        style.textContent = cssText;
        document.head.appendChild(style);
    }
    link.remove();
});

document.querySelectorAll("img").forEach(function(img) {
    if (!img.currentSrc || img.currentSrc.indexOf("data:") === 0) {
        return;
    }

    try {
        var canvas = document.createElement("canvas");
        var ctx = canvas.getContext("2d");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        ctx.drawImage(img, 0, 0);
        img.src = canvas.toDataURL();
    } catch (err) {
        console.log("Could not inline image", img.currentSrc, err);
    }
});

document.querySelectorAll("script").forEach(function(script) {
    script.remove();
});

return document.documentElement.outerHTML;
