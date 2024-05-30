document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById("package-form");
    form.addEventListener("submit", function(event) {
        event.preventDefault();
        const packageName = document.getElementById("package-name").value;
        
        fetch("/download", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: `package_name=${packageName}`
        })
        .then(response => {
            if (response.status === 200) {
                return response.blob();
            } else {
                throw new Error("Package not found");
            }
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            a.download = `${packageName}_dependencies.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(error => {
            alert(error.message);
        });
    });
});