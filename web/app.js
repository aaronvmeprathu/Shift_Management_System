const form = document.querySelector("#schedule-form");
const monthInput = document.querySelector("#month");
const results = document.querySelector("#results");
const errorMessage = document.querySelector("#error-message");

const leavesContainer = document.querySelector("#leaves-container");
const addLeaveBtn = document.querySelector("#add-leave-btn");

let loadedEmployees = [];

monthInput.value = new Date().toISOString().slice(0, 7);

// Update leave datepicker limits based on selected month
function updateLeaveDateLimits() {
  const monthVal = monthInput.value;
  if (!monthVal) return;
  const [year, month] = monthVal.split("-");
  const lastDay = new Date(year, month, 0).getDate();
  const minDate = `${monthVal}-01`;
  const maxDate = `${monthVal}-${String(lastDay).padStart(2, '0')}`;
  
  document.querySelectorAll(".leave-start-input").forEach(input => {
    input.min = minDate;
    input.max = maxDate;
  });
  document.querySelectorAll(".leave-end-input").forEach(input => {
    input.min = minDate;
    input.max = maxDate;
  });
}

monthInput.addEventListener("change", updateLeaveDateLimits);

// Dynamic Leave Row creation
function createLeaveRow() {
  const row = document.createElement("div");
  row.className = "leave-row";
  
  const select = document.createElement("select");
  select.className = "leave-employee-select";
  select.required = true;
  
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "Select Employee";
  select.appendChild(defaultOpt);
  
  loadedEmployees.forEach(emp => {
    const option = document.createElement("option");
    option.value = emp.id;
    option.textContent = `${emp.name} (${emp.id})`;
    select.appendChild(option);
  });
  
  const startDateInput = document.createElement("input");
  startDateInput.type = "date";
  startDateInput.className = "leave-start-input";
  startDateInput.required = true;
  
  const endDateInput = document.createElement("input");
  endDateInput.type = "date";
  endDateInput.className = "leave-end-input";
  endDateInput.required = true;
  
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "remove-leave-btn";
  removeBtn.innerHTML = "&times;";
  removeBtn.addEventListener("click", () => {
    row.remove();
  });
  
  row.appendChild(select);
  row.appendChild(startDateInput);
  row.appendChild(endDateInput);
  row.appendChild(removeBtn);
  
  leavesContainer.appendChild(row);
  
  // Set date picker limits for new row
  updateLeaveDateLimits();
}

addLeaveBtn.addEventListener("click", createLeaveRow);

// Fetch employees list to populate dropdown
async function fetchEmployees() {
  try {
    const response = await fetch("/api/employees");
    if (!response.ok) throw new Error("Failed to load employees");
    loadedEmployees = await response.json();
  } catch (error) {
    console.error("Error loading employees list:", error);
  }
}

// Initial setup
async function init() {
  await fetchEmployees();
  updateLeaveDateLimits();
}
init();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.textContent = "";
  const button = form.querySelector("button");
  const originalText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = "<span>Generating...</span>";
  const [year, month] = monthInput.value.split("-").map(Number);

  const leaves = [];
  let validationError = null;
  document.querySelectorAll(".leave-row").forEach(row => {
    const empId = row.querySelector(".leave-employee-select").value;
    const startVal = row.querySelector(".leave-start-input").value;
    const endVal = row.querySelector(".leave-end-input").value;
    if (!empId) {
      validationError = "Please select an employee for all leave rows.";
    } else if (!startVal || !endVal) {
      validationError = "Please select both start and end dates for all leaves.";
    } else if (endVal < startVal) {
      validationError = "Leave end date cannot be before start date.";
    }
    leaves.push({ employeeId: empId, startDate: startVal, endDate: endVal });
  });

  if (validationError) {
    errorMessage.textContent = validationError;
    button.disabled = false;
    button.innerHTML = originalText;
    return;
  }

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        year,
        month,
        leaves,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not create the schedule.");
    renderResults(data);
  } catch (error) {
    errorMessage.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = originalText;
  }
});

function renderResults(data) {
  document.querySelector("#month-label").textContent = data.monthLabel;
  document.querySelector("#schedule-download").href = data.downloads.schedule;
  document.querySelector("#summary-download").href = data.downloads.summary;
  document.querySelector("#employees-download").href = data.downloads.employees;
  renderMetrics(data.metrics);
  renderCalendar(data.schedule);
  renderTeam(data.employees);
  results.classList.remove("hidden");
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderMetrics(metrics) {
  const items = [
    [metrics.employees, "Total employees"],
    [metrics.seniors, "Senior developers"],
    [metrics.juniors, "Junior developers"],
    [metrics.operatingDays, "Calendar days"],
    [metrics.assignments, "Total assignments"],
  ];
  document.querySelector("#metrics").innerHTML = items
    .map(([number, label]) => `<div class="metric"><strong>${number}</strong><span>${label}</span></div>`)
    .join("");
}

function renderCalendar(schedule) {
  document.querySelector("#calendar").innerHTML = schedule
    .map((day) => {
      const shifts = day.shifts
        .map((shift) => {
          const empHtmlList = shift.employees
            .map(emp => `<span class="employee-item ${emp.level}">${emp.name}</span>`)
            .join(", ");
          return `<div class="shift ${shift.name}">
            <div class="shift-name">${shift.name}<span>${shift.count} staff</span></div>
            <div class="names">${empHtmlList}</div>
          </div>`;
        })
        .join("");

      const leavesSection = day.onLeave && day.onLeave.length > 0
        ? `<div class="day-leaves"><span>On Leave:</span> ${day.onLeave.join(", ")}</div>`
        : "";

      return `<article class="day-card">
        <div class="day-heading"><strong>${shortDate(day.date)}</strong><span>${day.day}</span></div>
        ${shifts}
        ${leavesSection}
      </article>`;
    })
    .join("");
}

function renderTeam(employees) {
  document.querySelector("#team-table").innerHTML = employees
    .map((employee) => `<tr>
      <td>${employee.employeeId}</td>
      <td><strong>${employee.name}</strong></td>
      <td><span class="badge ${employee.level}">${employee.level}</span></td>
      <td>${employee.gender}</td>
      <td><span class="badge ${employee.fixedShift}">${employee.fixedShift}</span></td>
      <td>${employee.workdays}</td><td><strong>${employee.daysOff}</strong></td>
      <td>${employee.leaveDays > 0 ? `<span class="badge leave">${employee.leaveDays} days</span>` : '-'}</td>
    </tr>`)
    .join("");
}

function shortDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    const showCalendar = tab.dataset.tab === "calendar";
    document.querySelector("#calendar-panel").classList.toggle("hidden", !showCalendar);
    document.querySelector("#team-panel").classList.toggle("hidden", showCalendar);
  });
});
