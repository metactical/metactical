const loginButton = document.getElementById("login-btn")
const logoutButton = document.getElementById("logout-btn")

const clockInButton = document.getElementById("clock-in-btn");
const clockOutButton = document.getElementById("clock-out-btn");

const prevButton = document.getElementById("prev-button")
const nextButton = document.getElementById("next-button")

let button_activation_delay = 1;

let logOutTimerToggled = false;

let payCycles;
let prevPayCycles = 0;
let shiftSelected = false;
let selectedDate;
let selectedShiftType = "";
let current_shift_name = "";

//Clockin
let selectedClockinLog;

let pageIndex = 0;
let countIndex = 0;

loginButton.onclick = login
logoutButton.onclick = logout
clockInButton.onclick = clockIn
clockOutButton.onclick = clockOut
prevButton.onclick = onPrevButton
nextButton.onclick = onNextButton

//Hide navbar
$("nav").hide()

frappe.ready(function () {
    //Check if clocked in on load
    if (frappe.session.user != "Guest") {
        //Validate button states if clocked in
        //onClockIn();
        //loginButton.classList.toggle('d-none');
        //logoutButton.classList.toggle('d-none');

        onLogin();
    }

    //Display buttons
    //clockInButton.classList.toggle('d-none');
    //clockOutButton.classList.toggle('d-none');
});

//Clock
let current_time;

function startTime() {
    const today = new Date();
    let h = today.getHours();
    let m = today.getMinutes();
    let s = today.getSeconds();
    m = checkTime(m);
    s = checkTime(s);
    document.getElementById('clock').innerHTML = h + ":" + m + ":" + s;
    current_time = h + ":" + m + ":" + s;
    setTimeout(startTime, 1000);
}

function checkTime(i) {
    if (i < 10) { i = "0" + i };  // add zero in front of numbers < 10
    return i;
}

startTime();

//Login
function login() {
    fetch(`${window.origin}/api/method/login`, {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            usr: document.getElementById('email').value,
            pwd: document.getElementById('password').value
        })
    })
        .then(r => r.json())
        .then(r => {
            console.log(r);
            if (r.message == 'Logged In') {
                //Login in success
                notify('success', 'Login success')
                onLogin()
            }

            else {
                //Login failed
                notify('danger', 'Invalid credentials')
            }
        })
}

function onLogin() {
    //Hide login fields
    hideLogin()

    //Hide login button
    loginButton.classList.toggle('d-none');

    //Show logout button
    logoutButton.classList.toggle('d-none');

    //Activate clockin button
    clockInButton.removeAttribute('disabled')

    //Activate clockin button
    clockInButton.classList.toggle("btn-success");
    clockInButton.classList.toggle("btn-secondary");

    //Show paycycle data
    //Call api after login
    const date = new Date();
    const today = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;

    frappe.call({
        method: "metactical.api.clockin.get_pay_cycle_data",
        args: {
            current_date: today,
            //current_time: current_time
        },
        callback: r => {
            console.log(r.message)

            if (r.message.pay_cycle_data_exists) {
                payCycles = r.message.pay_cycles
                prevPayCycles = r.message.pay_cycles.length - 1
                validateButtons()
                toggleTable()
                table(payCycles)
                checkClockinStatus()
            }

            else {
                notify("danger", "No data to display")
            }

        }
    })

    //table(payCycles)
}

function checkClockinStatus() {
    frappe.call({
        method: "metactical.api.clockin.get_clockin_status",
        callback: r => {
            console.log(r.message)
            if (r.message.clocked_in) {
                //grey out clockin button if success
                clockInButton.classList.toggle("btn-success");
                clockInButton.classList.toggle("btn-secondary");
                clockInButton.setAttribute("disabled", "");

                //red in clockout button if success
                clockOutButton.classList.toggle("btn-secondary");
                clockOutButton.classList.toggle("btn-danger");
                clockOutButton.removeAttribute("disabled");
            }
        }
    })
}

function logout() {
    fetch(`${window.origin}/api/method/logout`, {
        method: 'GET',
    })
        .then(r => r.json())
        .then(r => {
            console.log(r);

            //grey out clockout button if success
            //clockOutButton.classList.toggle("btn-danger");
            //clockOutButton.classList.toggle("btn-secondary");
            //clockOutButton.setAttribute("disabled", "");

            //green in clockin button if success
            //clockInButton.classList.toggle("btn-secondary");
            //clockInButton.classList.toggle("btn-success");
            //clockInButton.removeAttribute("disabled");
            //Display success message
            /* notify('danger', message);
            if (!document.getElementById("pay-cycle").classList.contains("d-none")) {
                toggleTable()
            } */
            //toggleTable()
            //showLogin()
            notify('success', 'Logout success')

            //Show login fields
            showLogin()

            //Check if clockedin
            if (clockOutButton.classList.contains("btn-danger")) {
                //Disable clock out button
                clockOutButton.classList.toggle("btn-danger")
                clockOutButton.classList.toggle("btn-secondary")
                clockOutButton.setAttribute("disabled", "true")
            }

            else {
                clockInButton.setAttribute('disabled', 'true')
                clockInButton.classList.toggle("btn-success");
                clockInButton.classList.toggle("btn-secondary");
            }

            //Hide logout button
            logoutButton.classList.toggle('d-none')

            //Show login button
            loginButton.classList.toggle('d-none')

            //Hide pay cycle data
            hidePayCycleData()

            //Clear field values
            $("#email").val("")
            $("#password").val("")
        })
}

function clockIn() {
    onClockIn()
    /* fetch(`${window.origin}/api/method/login`, {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            usr: document.getElementById('email').value,
            pwd: document.getElementById('password').value
        })
    })
        .then(r => r.json())
        .then(r => {
            console.log(r);
            if (r.message == 'Logged In') {
                //Clock in success
                onClockIn();
            }

            else {
                notify('danger', 'Invalid credentials')
            }
        }) */
}

function clockOut() {
    //Clockout/Log out

    const date = new Date();
    const today = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;

    frappe.call({
        method: "metactical.api.clockin.update_clockin_log",
        args: {
            current_date: today,
            to_time: current_time
        },
        callback: r => {
            console.log("Clocking out")
            console.log(r)
            onClockOut("Clockout success")
        }
    });
}

function onClockIn() {
    logOutTimerToggled = false

    //grey out clockin button if success
    clockInButton.classList.toggle("btn-success");
    clockInButton.classList.toggle("btn-secondary");
    clockInButton.setAttribute("disabled", "");

    //red in clockout button if success
    clockOutButton.classList.toggle("btn-secondary");
    clockOutButton.classList.toggle("btn-danger");
    clockOutButton.removeAttribute("disabled");

    //Call api
    const date = new Date();
    const today = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;

    console.log("Attempting to clockin")

    frappe.call({
        method: "metactical.api.clockin.check_current_pay_cycle_record",
        args: {
            current_date: today,
            current_time: current_time
        },
        callback: r => {
            console.log(r.message)
            //table(r.message.pay_cycles)
            if (r.message.clockin_status == 1) {
                //payCycles = r.message.pay_cycles
                //button_activation_delay = r.message.button_activation_delay
                //validateLogin()
                //prevPayCycles = r.message.pay_cycles.length - 1
                //validateButtons()
                //toggleTable()

                $("#starts-at").text(r.message.current_shift.start_time)
                $("#ends-at").text(r.message.current_shift.end_time)
                current_shift_name = r.message.current_shift.name

                //Display success message
                notify('success', 'Clockin success');
            }

            else {
                let message = "Clockin too early"

                //Log user out
                onClockOut(message)
            }
        }
    });
}

function onClockOut(message) {
    clockOutButton.classList.toggle("btn-danger");
    clockOutButton.classList.toggle("btn-secondary");
    clockOutButton.setAttribute("disabled", "");

    //green in clockin button if success
    clockInButton.classList.toggle("btn-secondary");
    clockInButton.classList.toggle("btn-success");
    clockInButton.removeAttribute("disabled");
    //Display success message
    notify('danger', message);

    startLogoutTimer()
    /* fetch(`${window.origin}/api/method/logout`, {
        method: 'GET',
    })
        .then(r => r.json())
        .then(r => {
            console.log(r);

            //grey out clockout button if success
            clockOutButton.classList.toggle("btn-danger");
            clockOutButton.classList.toggle("btn-secondary");
            clockOutButton.setAttribute("disabled", "");

            //green in clockin button if success
            clockInButton.classList.toggle("btn-secondary");
            clockInButton.classList.toggle("btn-success");
            clockInButton.removeAttribute("disabled");
            //Display success message
            notify('danger', message);
            if (!document.getElementById("pay-cycle").classList.contains("d-none")) {
                toggleTable()
            }
            //toggleTable()
            showLogin()
        }) */
}

function notify(type, message) {
    const dangerNotification = document.getElementById("danger-notification");
    const successNotification = document.getElementById("success-notification");

    if (type == 'success') {
        successNotification.textContent = message;
        successNotification.classList.toggle('d-none');

        setTimeout(() => {
            successNotification.classList.toggle('d-none');
        }, 5000);
    }

    else {
        dangerNotification.textContent = message;
        dangerNotification.classList.toggle('d-none');

        setTimeout(() => {
            dangerNotification.classList.toggle('d-none');
        }, 5000);
    }
}

const table = (tableData) => {
    const trh1 = $("#trh1")
    const trh2 = $("#trh2")

    const trb1 = $("#trb1")
    const trb2 = $("#trb2")
    const totalHoursWorked = $("#total-hours-worked")

    trh1.empty()
    trh2.empty()
    trb1.empty()
    trb2.empty()
    totalHoursWorked.empty()

    //let pageIndex = 0;
    countIndex = 0;

    //const numPayCycles = tableData.length 
    console.log(pageIndex)

    if (tableData[pageIndex].days.length > 6) {
        for (; countIndex <= 6; countIndex++) {
            trh1.append(`<th class="table-btn" scope="col">${dateFormatter(tableData[pageIndex].days[countIndex].date)}<span class='d-none'>${tableData[pageIndex].days[countIndex].date}</span></th>`)
            //trb1.append(`<td scope="col">${Math.round(tableData[pageIndex].days[countIndex].hours_worked)} hours</td>`)
            trb1.append(`<td scope="col">${tableData[pageIndex].days[countIndex].hours_worked.toFixed(2)} hours</td>`)
            console.log("looping")
        }
        console.log(trh1)
    }

    for (; countIndex < tableData[pageIndex].days.length; countIndex++) {
        trh2.append(`<th class="table-btn" scope="col">${dateFormatter(tableData[pageIndex].days[countIndex].date)}<span class='d-none'>${tableData[pageIndex].days[countIndex].date}</span></th>`)
        trb2.append(`<td scope="col">${tableData[pageIndex].days[countIndex].hours_worked.toFixed(2)} hours</td>`)
    }

    totalHoursWorked.text(`Total: ${Math.round(tableData[pageIndex].total_hours_worked)} hours`)

    validateButtons()
}

function dateFormatter(date) {
    const formattedDate = new Date(date).toDateString().slice(0, 10);
    return formattedDate;
}

const hideLogin = () => {
    //hide form
    const form = $("#auth")
    form.hide()
}

const hidePayCycleData = () => {
    //Hide Pay Cycle Table
    pc = document.getElementById("pay-cycle")
    if (!pc.classList.contains("d-none")) {
        toggleTable()
    }

    //Empty pay cycles array
    payCycles = []
}

const showLogin = () => {
    const form = $("#auth")
    form.show()
}

//const validateTable = () => { }

const validateButtons = () => {
    validatePrevButton();
    validateNextButton();
}

const validatePrevButton = () => {
    if (pageIndex >= prevPayCycles || prevPayCycles <= 0) {
        prevButton.setAttribute("disabled", "")
    }

    else {
        prevButton.removeAttribute("disabled")
    }
}

const validateNextButton = () => {
    if (pageIndex <= 0) {
        nextButton.setAttribute("disabled", "")
    }

    else {
        nextButton.removeAttribute("disabled")
    }
}

function onPrevButton() {
    pageIndex += 1
    table(payCycles)
}

function onNextButton() {
    pageIndex -= 1
    table(payCycles)
}

function buttonActivationDelay(button) {
    button.setAttribute("disabled", "")

    setTimeout(() => {
        button.removeAttribute("disabled")
    }, button_activation_delay * 1000)
}

function toggleTable() {
    const payCycleTable = document.getElementById("pay-cycle")
    payCycleTable.classList.toggle("d-none")
}

$("body").on("click", ".table-btn", function () {
    //alert("Clicked")    
    console.log($(this).children("span").text())
    getDateDetails($(this).children("span").text())
    selectedDate = dateFormatter($(this).children("span").text())
})

function getDateDetails(date) {
    frappe.call({
        method: "metactical.api.clockin.get_date_details",
        args: {
            date: date
        },
        callback: r => {
            displayDateDetails(date, r.message.clockins)
            /* shift_info = document.getElementById("shift-info")
            
            if(shift_info.classList.contains("d-none")) {
                shift_info.classList.toggle("d-none")
            } */
        }
    })
}

function displayDateDetails(date, clockins) {
    let dateDetails = $("#details")
    dateDetails.empty()

    // console.log("Clockins")
    // console.log(clockins)

    dateDetails.append(`<span class="font-weight-bold">Date: </span><span>${dateFormatter(date)}</span>`)

    for (let i = 0; i < clockins.length; i++) {
        dateDetails.append(`
            <div class="clockin-log">
                <div><p class="font-weight-bold">Clocked In: </p><span class="clockin-time-12">${sliceAndConvertTimeTo12(clockins[i].from_time)}</span></div>
                <div><p class="font-weight-bold">Clocked Out: </p><span class="clockout-time-12">${sliceAndConvertTimeTo12(clockins[i].to_time)}</span></div>    

                <div class="d-none"><p class="font-weight-bold">Clocked In: </p><span class="clockin-time-24">${sliceTime(clockins[i].from_time)}</span></div>
                <div class="d-none"><p class="font-weight-bold">Clocked Out: </p><span class="clockout-time-24">${sliceTime(clockins[i].to_time)}</span></div>
                <span class="name d-none">${clockins[i].name}</span>
            </div>
        `)
    }
}

function sliceTime(time) {
    let slicedTime;
    console.log(time)
    if (time.length == 7) {
        let fullLengthTime = `0${time}`
        slicedTime = `${fullLengthTime.slice(0, 5)}`
    }

    else {
        slicedTime = `${time.slice(0, 5)}`
    }

    return slicedTime;
}


//Convert time to 12 hours format
function sliceAndConvertTimeTo12(time) {
    let slicedTime;
    console.log(time)
    if (time.length == 7) {
        let fullLengthTime = `0${time}`
        slicedTime = `${fullLengthTime.slice(0, 5)}`
    }

    else {
        slicedTime = `${time.slice(0, 5)}`
    }

    //return slicedTime;
    var dt = new Date(`2023-01-01 ${slicedTime}`);
    var hours = dt.getHours(); // gives the value in 24 hours format
    //console.log(dt)

    var AmOrPm = hours >= 12 ? 'PM' : 'AM';
    hours = (hours % 12) || 12;
    var minutes = dt.getMinutes();
    var finalTime = hours + ":" + minutes + " " + AmOrPm;
    return finalTime
}

//Convert time to military format
function convertTimeToMilitary(timeStr) {
    const [time, modifier] = timeStr.split(' ');
    let [hours, minutes] = time.split(':');
    if (hours === '12') {
        hours = '00';
    }
    if (modifier === 'PM') {
        hours = parseInt(hours, 10) + 12;
    }
    return `${hours}:${minutes}`;
}

//To modify
/* $("body").on("click", ".dropdown-item", function () {
    $("#select-shift-button").text($(this).children(".shift-time").text())
    selectedShiftType = $(this).children(".shift-name").text()
    shiftSelected = true
}) */

//To modify
/* $("body").on("click", "#request-details-change-button", function () {
    frappe.call({
        method: "metactical_time_tracker.api.get_shifts",
        args: {
            current_shift_name: current_shift_name
        },
        callback: r => {
            console.log(r.message)
            $("#shifts").empty()
 
            for (let i = 0; i < r.message.shifts.length; i++) {
                //const element = r.message.shifts[i];
                $("#shifts").append(
                    `<p class="dropdown-item">
                        <span class="shift-time">${sliceTime(r.message.shifts[i].start_time)} - ${sliceTime(r.message.shifts[i].end_time)}</span>
                        <span class="shift-name d-none">${r.message.shifts[i].name}</span>
                    </p>`)
            }
        }
    })
}) */

//To modify
/* $("body").on("click", "#shift-change-submit", function() {
    //let shift_type = $("#shifts").text($(this).children(".shift-time").text())
 
    console.log(selectedShiftType)
    frappe.call({
        method: "metactical_time_tracker.api.shift_request",
        args: {
            "shift_type": selectedShiftType,
            "date": selectedDate
        },
        callback: r => {
            console.log(r.message)
            $("#change-shift-modal").modal("hide")
            $("#success-modal").modal("show")
        }
    })
}) */

//When clockin log is clicked
$("body").on("click", ".clockin-log", function () {
    selectedClockinLog = $(this)//.children(".d-none")
    //console.log($(this).find(".clockin-time").text())
    $("#selected-clockin-log").empty()
    $("#selected-clockin-log").append(
        `
            <p><b>CheckIn: </b>${selectedClockinLog.find(".clockin-time-12").text()}</p>
            <p><b>CheckOut: </b>${selectedClockinLog.find(".clockout-time-12").text()}</p>
        `
    )

    console.log(selectedClockinLog.find(".d-none").text())

    shift_info = document.getElementById("shift-info")

    if (shift_info.classList.contains("d-none")) {
        shift_info.classList.toggle("d-none")
    }
})

$("body").on("click", "#submit-time-change", function (event) {
    event.preventDefault()
    const checkInTime12 = `${$("#check-in-hours").val()}:${$("#check-in-minutes").val()} ${$("#check-in-am-pm").val()}`
    const checkInTimeMilitary = convertTimeToMilitary(checkInTime12)

    const checkOutTime12 = `${$("#check-out-hours").val()}:${$("#check-out-minutes").val()} ${$("#check-out-am-pm").val()}`
    const checkOutTimeMilitary = convertTimeToMilitary(checkOutTime12)

    //New
    console.log(checkInTime12)
    console.log(checkInTimeMilitary)
    console.log(checkOutTime12)
    console.log(checkOutTimeMilitary)

    //Current
    const currentCheckIn12 = selectedClockinLog.find('.clockin-time-12').text()
    const currentCheckOut12 = selectedClockinLog.find('.clockout-time-12').text()

    const log_name = selectedClockinLog.find(".name.d-none").text()

    frappe.call({
        method: "metactical.api.clockin.send_details_change_request",
        args: {
            "log_name": log_name,
            "checkInTime12": checkInTime12,
            "checkInTimeMilitary": checkInTimeMilitary,
            "checkOutTime12": checkOutTime12,
            "checkOutTimeMilitary": checkOutTimeMilitary,
            "currentCheckIn12": currentCheckIn12,
            "currentCheckOut12": currentCheckOut12,
            "date": selectedDate
        },
        callback: r => {
            console.log(r.message)
            $("#change-details-modal").modal("hide")
            $("#success-modal").modal("show")
        }
    })
})

//Enter is pressed
$(document).on('keypress', function (e) {
    if (e.which == 13) {
        if ($("#email").is(":focus") || $("#password").is(":focus")) {
            login()
        }
    }
});

function startLogoutTimer() {
    console.log("Logout timer started")
    logOutTimerToggled = true
    frappe.call({
        method: "metactical.api.clockin.get_logout_delay",
        callback: r => {
            console.log(r.message)
            if (r.message.logout_delay > 1) {
                console.log("Waiting")
                let logout_delay = r.message.logout_delay * 1000
                setTimeout(() => {
                    if (logOutTimerToggled) {
                        //window.alert("Logged out")
                        logout()
                    }
                }, logout_delay)
            }
        }
    })
}