// Simple client-side setup wizard for Rhocom Hotel
(function () {
    // Ensure frappe is available
    if (typeof frappe === "undefined") return;

    const STEPS = [
        {
            id: "room_types",
            title: "Create Room Types",
            description: "Define room types (capacity, extra beds) that rooms will use.",
            doctype: "Hotel Room Type",
        },
        {
            id: "pricing",
            title: "Set Pricing",
            description: "Create Hotel Room Pricing records and pricing items for date ranges.",
            doctype: "Hotel Room Pricing",
        },
        {
            id: "packages",
            title: "Create Packages",
            description: "Map items (packages) to room types so reservations can reference them.",
            doctype: "Hotel Room Package",
        },
    ];

    function getKey(id) {
        return `rhohotel.setup.${id}`;
    }

    function isDone(id) {
        return localStorage.getItem(getKey(id)) === "1";
    }

    function setDone(id, v) {
        localStorage.setItem(getKey(id), v ? "1" : "0");
    }

    function render() {
        const container = document.querySelector("#rhohotel-wizard");
        if (!container) return;
        container.innerHTML = "";

        const list = document.createElement("div");
        list.className = "list-group";

        STEPS.forEach((step, i) => {
            const item = document.createElement("div");
            item.className = "list-group-item";
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.style.alignItems = "center";
            item.innerHTML = `
				<div>
					<strong>${i + 1}. ${step.title}</strong>
					<div class="small text-muted">${step.description}</div>
				</div>
			`;

            const actions = document.createElement("div");
            actions.style.display = "flex";
            actions.style.gap = "0.5rem";

            const openBtn = document.createElement("button");
            openBtn.className = "btn btn-primary btn-sm";
            openBtn.innerText = `Open ${step.doctype} form`;
            openBtn.onclick = () => frappe.set_route("Form", step.doctype, "new");

            const doneBtn = document.createElement("button");
            doneBtn.className = isDone(step.id) ? "btn btn-success btn-sm" : "btn btn-outline-secondary btn-sm";
            doneBtn.innerText = isDone(step.id) ? "Done" : "Mark done";
            doneBtn.onclick = () => {
                setDone(step.id, !isDone(step.id));
                render();
            };

            actions.appendChild(openBtn);
            actions.appendChild(doneBtn);
            item.appendChild(actions);
            list.appendChild(item);
        });

        const footer = document.createElement("div");
        footer.style.marginTop = "1rem";
        footer.innerHTML = `
			<div>
				<button id="rhohotel-reset" class="btn btn-warning btn-sm">Reset progress</button>
				<span class="ml-2 small text-muted">When you finish all steps, open <a href="#/desk#Form/Hotel Room Reservation/new">New Reservation</a>.</span>
			</div>
		`;

        list.appendChild(footer);
        container.appendChild(list);

        document.querySelector("#rhohotel-reset").onclick = () => {
            STEPS.forEach(s => setDone(s.id, false));
            render();
        };
    }

    frappe.ready(() => {
        render();
    });

})();
