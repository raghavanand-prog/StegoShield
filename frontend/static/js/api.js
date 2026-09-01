/* Thin fetch wrapper for the StegoShield JSON API. */

const StegoAPI = (() => {
    async function _handle(response) {
        let data;
        try {
            data = await response.json();
        } catch (e) {
            throw new Error("Server returned an unexpected response.");
        }
        if (!response.ok) {
            const message = (data && data.error && data.error.message) || "Request failed.";
            const err = new Error(message);
            err.code = data && data.error && data.error.code;
            err.status = response.status;
            throw err;
        }
        return data;
    }

    async function postForm(path, formData) {
        const response = await fetch(`/api${path}`, { method: "POST", body: formData });
        return _handle(response);
    }

    async function get(path) {
        const response = await fetch(`/api${path}`);
        return _handle(response);
    }

    return { postForm, get };
})();
