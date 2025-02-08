const socket = io(window.location.origin);


// Обновление статуса
socket.on("status_update", (data) => {
    const statusDiv = document.getElementById("status");
    if (data.status === "good") {
        statusDiv.textContent = "✔ Успешно";
        statusDiv.className = "success";



    } else {
        statusDiv.textContent = "✘ Ошибка";
        statusDiv.className = "error";
    }
});

// Слушаем событие для редиректа
socket.on('redirect_to_good', function(data) {
    if (data.status === "good") {
        window.location.href = "/good";  // Переходим на новую страницу
    }
});