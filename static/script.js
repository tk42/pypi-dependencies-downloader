document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById("package-form");
    form.addEventListener("submit", function(event) {
        event.preventDefault();
        const packageName = document.getElementById("package-name").value;
        const bucketName = document.getElementById("bucket-name").value;
        
        fetch("/upload", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: `package_name=${packageName}&bucket_name=${bucketName}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.s3_url) {
                alert(`File uploaded to S3: ${data.s3_url}`);
            } else {
                alert("Failed to upload file");
            }
        })
        .catch(error => {
            alert(error.message);
        });
    });
});