// DestinationChoiceUI «boundary»: several places match the destination (UC-01 AF1, UC-02 AF1).
// The Driver picks one; its coordinates go back to the backend as destination_location.
class DestinationChoiceUI {
  constructor({ onPick, onBack }) {
    this.onPick = onPick;
    $("#btn-choice-back").addEventListener("click", () => onBack());
  }

  show(query, matches) {
    $("#choice-query").textContent = `${matches.length} places match "${query}".`;
    $("#choice-list").replaceChildren(...matches.map((match) => h("li", {},
      h("button", { type: "button", class: "choice", onclick: () => this.itemSelectClick(match) },
        h("strong", {}, match.name),
        match.address && h("span", { class: "muted" }, match.address)))));
    $("#choice-list button")?.focus();
  }

  itemSelectClick(match) {
    this.onPick(match);
  }
}
