// Contacto y datos del sitio. Un solo sitio que tocar.
export const contacto = {
  whatsapp: '34633505153',
  whatsappVisible: '+34 633 50 51 53',
  email: 'hola@impulcan.com',
  zona: 'Las Palmas de Gran Canaria',
};

export function enlaceWhatsapp(mensaje) {
  const base = `https://wa.me/${contacto.whatsapp}`;
  return mensaje ? `${base}?text=${encodeURIComponent(mensaje)}` : base;
}
