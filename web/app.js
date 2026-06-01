const form = document.querySelector("#schedule-form");
const monthInput = document.querySelector("#month");
const results = document.querySelector("#results");
const errorMessage = document.querySelector("#error-message");

monthInput.value = new Date().toISOString().slice(0, 7);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.textContent = "";
  const button = form.querySelector("button");
  const originalText = button.innerHTML;
  button.disabled = true;
  button.innerHTML = "<span>Generating...</span>";
  const [year, month] = monthInput.value.split("-").map(Number);

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        year,
        month,
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
        .map((shift) => `<div class="shift ${shift.name}">
          <div class="shift-name">${shift.name}<span>${shift.count} staff</span></div>
          <div class="names">${shift.employees.join(", ")}</div>
        </div>`)
        .join("");
      return `<article class="day-card">
        <div class="day-heading"><strong>${shortDate(day.date)}</strong><span>${day.day}</span></div>
        ${shifts}
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
