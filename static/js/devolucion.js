document.addEventListener("DOMContentLoaded", function () {

    // ===== BUSCADOR TABLA =====

    const buscador = document.getElementById("buscador");
    const filas = document.querySelectorAll("#tablaDevoluciones tbody tr");

    if (buscador) {

        buscador.addEventListener("keyup", function () {

            let texto = buscador.value.toLowerCase();

            filas.forEach(function (fila) {

                let producto = fila.querySelector(".producto");

                if (producto) {

                    let nombreProducto =
                        producto.textContent.toLowerCase();

                    if (nombreProducto.includes(texto)) {

                        fila.style.display = "";

                    } else {

                        fila.style.display = "none";

                    }

                }

            });

        });

    }

    // ===== CLIENTE =====

    const buscadorCliente =
        document.getElementById("buscadorCliente");

    const idCliente =
        document.getElementById("idCliente");

    if (buscadorCliente && idCliente) {

        buscadorCliente.addEventListener("change", function () {

            const opciones =
                document.querySelectorAll("#listaClientes option");

            idCliente.value = "";

            opciones.forEach(function (opcion) {

                if (opcion.value === buscadorCliente.value) {

                    idCliente.value =
                        opcion.dataset.id;

                }

            });

        });

    }

    // ===== PRODUCTO =====

    const buscadorProducto =
        document.getElementById("buscadorProducto");

    const idProducto =
        document.getElementById("idProducto");

    if (buscadorProducto && idProducto) {

        buscadorProducto.addEventListener("change", function () {

            const opciones =
                document.querySelectorAll("#listaProductos option");

            idProducto.value = "";

            opciones.forEach(function (opcion) {

                if (opcion.value === buscadorProducto.value) {

                    idProducto.value =
                        opcion.dataset.id;

                }

            });

        });

    }

});