document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById("package-form");
    form.addEventListener("submit", function(event) {
        event.preventDefault();
        const packageList = document.getElementById("package-list").value;
        const bucketName = document.getElementById("bucket-name").value;
        const packageType = document.getElementById("package-type").value;
        if (!packageList || !bucketName || !packageType) {
            alert("Please fill in all fields.");
            return;
        }
        if (!confirm("Are you sure you want to upload these files?")) {
            return;
        }
        fetch("/upload", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                package_list: packageList,
                bucket_name: bucketName,
                package_type: packageType
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw err; });
            }
            return response.json();
        })
        .then(data => {
            if (data.s3_url) {
                alert(`File uploaded to S3: ${data.s3_url}`);
            } else {
                alert("Failed to upload file");
            }
        })
        .catch(error => {
            if (error.detail) {
                alert(`Error: ${error.detail}`);
            } else if (error.message) {
                alert(`Error: ${error.message}`);
            } else {
                alert("An unexpected error occurred.");
            }
        });
    });
});